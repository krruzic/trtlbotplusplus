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
    transactionData = rpc.getTransactions(firstBlockIndex=starting_height-10, blockCount=15) # include bets from previous gap block
    for item in transactionData['items']:
        for tx in item['transactions']:
            if tx['paymentId'] == '':
                continue
            if tx['transactionHash'] in CONFIRMED_TXS:
                continue
            if tx['unlockTime'] == 0:
                CONFIRMED_TXS.append({'transactionHash': tx['transactionHash'],'ready':True})
            if tx['unlockTime'] != 0:
                CONFIRMED_TXS.append({'transactionHash': tx['transactionHash'],'ready':False})
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
        for transfer in data['transaction']['transfers']:
            if transfer['address'] in rpc.getAddresses()['addresses']:
                amount += transfer['amount']
        if not balance:
            t = TipJar(pid, ctx.message.author.id, amount)
            print(t)
            session.add(t)
            session.commit()
        else:
            balance.amount = balance.amount + amount
        nt = Transaction(tx['transactionHash'])
        session.add(nt)
        session.commit()
        CONFIRMED_TXS.pop(i)

def get_fee(amount):
    if amount < 10000000:
        fee = 100
    elif amount > 10000000 and amount < 30000000:
        fee = 1000
    elif amount > 30000000:
        fee = 3000

def build_transfer(address, amount):
    params = {
        'fee': get_fee(amount),
        'anonymity': 3,
        'transfers': [
            'amount': amount,
            'address': address
        ]
    }
    return params