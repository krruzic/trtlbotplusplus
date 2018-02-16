from sqlalchemy import Table, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Wallet(Base):

    __tablename__ = 'wallets'

    id          =   Column(Integer, primary_key=True)
    address     =   Column(String(99), unique=True, nullable=False)
    userid      =   Column(Integer, default=-1)
    messageid   =   Column(Integer, default=0)
    deposit     =   Column(String(99), unique=True, nullable=True)

    def __repr__(self):
        return "<User {} has Wallet {}>".format(self.userid,self.address)

    def __init__(self, address, userid, messageid):
        self.address = address
        self.userid = int(userid)
        self.messageid = int(messageid)

class TipJar(Base):

    __tablename__ = 'tips'

    id          =   Column(Integer, primary_key=True)
    paymentid   =   Column(String(64), unique=True, nullable=False)
    userid      =   Column(Integer, default=-1)
    amount      =   Column(Integer, default=0)

    def __repr__(self):
        return "<User {} has {} available to tip>".format(self.userid, self.amount)

    def __init__(self, paymentid, userid, amount):
        self.paymentid = paymentid
        self.userid = int(userid)
        self.amount = int(amount)

class Transaction(Base):

    __tablename__ = 'transactions'

    id          =   Column(Integer, primary_key=True)
    tx          =   Column(String(128), unique=True, nullable=False)

    def __repr__(self):
        return "<txt hash {}>".format(self.tx)

    def __init__(self, tx):
        self.tx = tx
