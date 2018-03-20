import random
import sys
import binascii
import json
from collections import deque

from jsonrpc_requests import Server


from models import Transaction, TipJar

config = json.load(open('config.json'))


class TrtlServer(Server):
    def dumps(self, data):
        data['password'] = config['rpc_password']
        return json.dumps(data)


rpc = TrtlServer("http://{}:{}/json_rpc".format(config['rpc_host'], config['rpc_port']))
daemon = TrtlServer("http://{}:{}/json_rpc".format(config['daemon_host'], config['daemon_port']))
CONFIRMED_TXS = []


def get_supply():
    lastblock = daemon.getlastblockheader()
    bo = daemon.f_block_json(hash=lastblock["block_header"]["hash"])
    return float(bo["block"]["alreadyGeneratedCoins"])/100


def format_hash(hashrate):
    i = 0
    byteUnits = [" H", " KH", " MH", " GH", " TH", " PH"]
    while (hashrate > 1000):
        hashrate = hashrate / 1000
        i = i+1
    return "{0:,.2f} {1}".format(hashrate, byteUnits[i])


def gen_paymentid(address):
    rng = random.Random(address+config['token'])
    length = 32
    chunk_size = 65535
    chunks = []
    while length >= chunk_size:
        chunks.append(rng.getrandbits(chunk_size * 8).to_bytes(chunk_size, sys.byteorder))
        length -= chunk_size
    if length:
        chunks.append(rng.getrandbits(length * 8).to_bytes(length, sys.byteorder))
    result = b''.join(chunks)

    return "".join(map(chr, binascii.hexlify(result)))


def get_deposits(starting_height, session):
    print("scanning deposits at block: ", starting_height)
    transactionData = rpc.getTransactions(firstBlockIndex=starting_height, blockCount=1000)
    for item in transactionData['items']:
        for tx in item['transactions']:
            if tx['paymentId'] == '':
                continue
            if tx['transactionHash'] in CONFIRMED_TXS:
                continue
            if tx['unlockTime'] <= 3:
                CONFIRMED_TXS.append({'transactionHash': tx['transactionHash'],'ready':True, 'pid': tx['paymentId']})
            elif tx['unlockTime'] > 3:
                CONFIRMED_TXS.append({'transactionHash': tx['transactionHash'],'ready':False, 'pid': tx['paymentId']})
    for i,trs in enumerate(CONFIRMED_TXS):
        processed = session.query(Transaction).filter(Transaction.tx == trs['transactionHash']).first()
        amount = 0
        print("Looking at tx: " + trs['transactionHash'])
        if processed:
            print("already processed: " + trs['transactionHash'])
            CONFIRMED_TXS.pop(i)
            continue
        data = rpc.getTransaction(transactionHash=trs['transactionHash'])
        if not trs['ready']:
            if data['unlockTime'] != 0:
                continue
            else:
                trs['ready'] = True
        likestring = data['transaction']['paymentId'][0:58]
        balance = session.query(TipJar).filter(TipJar.paymentid.contains(likestring)).first()
        print("Balance for pid {} is: {}".format(likestring,balance))
        if not balance:
            print("user does not exist!")
            continue
        og_balance = balance.amount
        for transfer in data['transaction']['transfers']:
            print("updating user balance!")
            address = transfer['address']
            amount = transfer['amount']
            change = 0
            if address in rpc.getAddresses()['addresses']:
                if trs['pid']==balance.paymentid: # money entering tipjar, add to user balance
                    print("deposit of {}".format(amount))
                    print("Depositing to: {}".format(balance.paymentid))
                    change += amount
            elif address != "" and trs['pid'] == (balance.paymentid[0:58] + balance.withdraw): # money leaving tipjar, remove from user's balance
                print("withdrawal of {}".format(amount))
                change -= (amount+data['transaction']['fee'])
            try:
                balance.amount += change
            except:
                print("no balance, setting balance to: {}".format(change))
                balance.amount = change
        print("new balance: {}".format(balance.amount))
        session.commit()
        if balance:
            nt = Transaction(trs['transactionHash'], balance.amount-og_balance, trs['pid'])
            CONFIRMED_TXS.pop(i)
            yield nt


def get_fee(amount):
    return 10


def build_transfer(amount, transfers, balance):
    print("SEND PID: {}".format(balance.paymentid[0:58] + balance.withdraw))
    params = {
        'addresses': [rpc.getAddresses()['addresses'][0]],
        'fee': get_fee(amount),
        'paymentId': balance.paymentid[0:58] + balance.withdraw,
        'anonymity': 3,
        'transfers': transfers
    }
    return params


def is_address(addr):
    """
    Does some basic validation on an object to check if it could be an address.
    """
    return type(addr) is str and addr.startswith('TRTL') and len(addr) == 99


REACTION_AMP_CACHE = deque([], 500)


def reaction_tip_lookup(message):
    for x in REACTION_AMP_CACHE:
        if x['msg'] == message:
            return x


def reaction_tip_register(message, user):
    msg = reaction_tip_lookup(message)
    if not msg:
        msg = {'msg': message, 'tips': []}
        REACTION_AMP_CACHE.append(msg)

    msg['tips'].append(user)

    return msg


def reaction_tipped_already(message, user):
    msg = reaction_tip_lookup(message)
    if msg:
        return user in msg['tips']
