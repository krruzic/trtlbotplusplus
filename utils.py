import random
import sys
import os
import binascii
import json

from jsonrpc_requests import Server, ProtocolError

from models import Transaction, TipJar


config = json.load(open('config.json'))
if 'rpc_port' in config:
    rpc_port = config['rpc_port']
else:
    rpc_port = ""
rpc = Server("http://127.0.0.1:{}/json_rpc".format(rpc_port))
daemon = Server("http://127.0.0.1:11898/json_rpc")
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
    return str(round(hashrate,2)) + byteUnits[i]

def gen_paymentid(address):
    rng = random.Random(address+config['token'])
    results = []
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
    print("scanning deposits")
    transactionData = rpc.getTransactions(firstBlockIndex=starting_height-10, blockCount=1000)
    print(transactionData)
    for item in transactionData['items']:
        for tx in item['transactions']:
            if tx['paymentId'] == '':
                continue
            if tx['transactionHash'] in CONFIRMED_TXS:
                continue
            if tx['unlockTime'] <= 3:
                CONFIRMED_TXS.append({'transactionHash': tx['transactionHash'],'ready':True, 'pid': tx['paymentId']})
            if tx['unlockTime'] > 3:
                CONFIRMED_TXS.append({'transactionHash': tx['transactionHash'],'ready':False, 'pid': tx['paymentId']})
        print("appended all txs to list... {}".format(len(CONFIRMED_TXS)))
    for i,trs in enumerate(CONFIRMED_TXS):
        print(trs)
        processed = session.query(Transaction).filter(Transaction.tx == trs['transactionHash']).first()
        amount = 0
        if processed:
            CONFIRMED_TXS.pop(i)
            continue
        data = rpc.getTransaction(transactionHash=trs['transactionHash'])
        print("data from RPC:")
        print(data)
        if not trs['ready']:
            if data['unlockTime'] != 0:
                continue
            else:
                trs['ready'] = True
        likestring = data['transaction']['paymentId'][0:58]
        print(likestring)
        balance = session.query(TipJar).filter(TipJar.paymentid.contains(likestring)).first()
        if not balance:
            print("user does not exist!")
            continue
        for transfer in data['transaction']['transfers']:
            print("updating user balance!")
            address = transfer['address']
            amount = transfer['amount']
            change = 0
            if address in rpc.getAddresses()['addresses']:
                print("deposit of {}".format(amount))
                change += amount
            elif address != "" and trs['pid'] == (balance.paymentid[0:58] + balance.withdraw): # money leaving tipjar, remove from user's balance
                print("withdrawal of {}".format(amount))
                change -= (amount+data['transaction']['fee'])
            try:
                balance.amount += change
            except:
                balance.amount = change
        print("new balance: {}".format(balance.amount))
        session.commit()
        nt = Transaction(trs['transactionHash'])
        CONFIRMED_TXS.pop(i)
        yield nt

def get_fee(amount):
    if amount < 10000:
        return 10
    else:
        return amount*0.01

def build_transfer(address, amount, self_address, balance):
    print("SEND PID: {}".format(balance.paymentid[0:58] + balance.withdraw))
    params = {
        'fee': get_fee(amount),
        'paymentId': balance.paymentid[0:58] + balance.withdraw,
        'anonymity': 3,
        'transfers': [
            {
                'amount': amount,
                'address': address
            }
        ]
    }
    return params
