import random
import sys
import os
import binascii
import json

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
    transactionData = rpc.getTransactions({'firstBlockIndex':starting_height-1}) # include bets from previous gap block
    for item in transactionData['result']['items']:
        for tx in item['transactions']:
            if tx['paymentId']=='':
                continue
            if tx['transaction_hash'] in CONFIRMED_TXS:
                continue
            if tx['unlockTime']==0:
                CONFIRMED_TXS.append({'txid': tx['transaction_hash'],'parsed':True})
            if tx['unlockTime']!=0:
                CONFIRMED_TXS.append({'txid': tx['transaction_hash'],'parsed':False})

    for tx in CONFIRMED_TXS:
        if tx['parsed']:
            continue
        data = WALLET.getTransaction({'transactionHash':tx})
        balance = session.query(TipJar).filter(TipJar.paymentid == data['paymentId']).first()
        if not balance:
            t = TipJar(pid, ctx.message.author.id, 0)

        amount = data['amount']