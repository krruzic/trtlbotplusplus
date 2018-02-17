import random
import sys
import os
import binascii
import json

from jsonrpc_requests import Server

from models import Transaction, TipJar
class TrtlServer(Server):
    def dumps(self, data):
        data['password'] = config['rpc_password']
        return json.dumps(data)

config = json.load(open('config.json'))
if 'rpc_port' in config:
    rpc_port = config['rpc_port']
else:
    rpc_port = "8070"
rpc = TrtlServer("http://127.0.0.1:{}/json_rpc".format(rpc_port))
daemon = TrtlServer("http://127.0.0.1:11898/json_rpc")
CONFIRMED_TXS = []

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
    transactionData = rpc.getTransactions(firstBlockIndex=starting_height-10, blockCount=1000) # include bets from previous gap block
    for item in transactionData['items']:
        for tx in item['transactions']:
            if tx['paymentId'] == '':
                continue
            if tx['transactionHash'] in CONFIRMED_TXS:
                continue
            if tx['unlockTime'] == 0:
                CONFIRMED_TXS.append({'transactionHash': tx['transactionHash'],'ready':True, 'pid': tx['paymentId']})
            if tx['unlockTime'] != 0:
                CONFIRMED_TXS.append({'transactionHash': tx['transactionHash'],'ready':False, 'pid': tx['paymentId']})
            print("appended all txs to list... {}".format(len(CONFIRMED_TXS)))
    for i,tx in enumerate(CONFIRMED_TXS):
        processed = session.query(Transaction).filter(Transaction.tx == tx['transactionHash']).first()
        amount = 0
        if processed:
            CONFIRMED_TXS.pop(i)
            continue
        data = rpc.getTransaction(transactionHash=tx['transactionHash'])
        print(data)
        if not tx['ready']:
            if data['unlockTime'] != 0:
                continue
            else:
                tx['ready'] = True
        balance = session.query(TipJar).filter(TipJar.paymentid == data['transaction']['paymentId']).first()
        if not balance:
            continue
        for transfer in data['transaction']['transfers']:
            address = transfer['address']
            amount = transfer['amount']
            change = 0
            if address in rpc.getAddresses()['addresses']:
                change += amount
            elif address != '' and tx['paymentId'] == (balance.paymentid[0:59] + balance.withdraw): # money leaving tipjar, remove from user's balance
                change -= amount
        balance.amount += change
        session.commit()
        nt = Transaction(tx['transactionHash'])
        CONFIRMED_TXS.pop(i)
        yield nt

def get_fee(amount):
    if amount < 10000000:
        return 10
    elif amount > 10000000 and amount < 30000000:
        return 100
    elif amount > 30000000:
        return 300

def build_transfer(address, amount, self_address):
    balance = session.query(TipJar).filter(TipJar.paymentid == gen_paymentid(self_address)).first()
    params = {
        'fee': get_fee(amount),
        'paymentId': balance.paymentid[0:59] + balance.withdraw,
        'anonymity': 3,
        'transfers': [
            {
                'amount': amount,
                'address': address
            }
        ]
    }
    return params
