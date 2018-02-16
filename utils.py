import random
import sys
import os
import binascii
import json

config = json.load(open('config.json'))

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
    length = 31
    chunk_size = 65535
    chunks = []
    while length >= chunk_size:
        chunks.append(rng.getrandbits(chunk_size * 8).to_bytes(chunk_size, sys.byteorder))
        length -= chunk_size
    if length:
        chunks.append(rng.getrandbits(length * 8).to_bytes(length, sys.byteorder))
    result = b''.join(chunks)

    for i in range(0,num):
        results.append("".join(map(chr, binascii.hexlify(result+(i).to_bytes(1, byteorder='big')))))

    return results