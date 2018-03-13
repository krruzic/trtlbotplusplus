import asyncio
import os
import json
import random

import discord
from discord.ext.commands import Bot
from discord.ext import commands
import platform
import requests

from sqlalchemy.engine import Engine
from sqlalchemy import event
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


from models import Wallet, TipJar, Transaction, Base
from utils import config, format_hash, gen_paymentid, rpc, daemon, get_deposits, get_fee, build_transfer, get_supply

HEADERS = {'Content-Type': 'application/json'}

### SETUP ###
engine = create_engine('sqlite:///trtl.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()


async def wallet_watcher():
    start = int(rpc.getStatus()['blockCount'])-10000
    while not client.is_closed:
        height = int(rpc.getStatus()['blockCount'])
        for tx in get_deposits(start, session):
            session.add(tx)
        try:
            session.commit()
        except:
            session.rollback()
        if start < height:
            start += 1000
        if start >= height:
            start = height-1
        await asyncio.sleep(25) # just less than the block time


client = Bot(description="TRTL Tipping Bot", command_prefix=config['prefix'], pm_help = False)
client.loop.create_task(wallet_watcher())

@client.event
async def on_ready():
    print("Bot online!")


### MARKET COMMANDS ###
@client.command()
async def faucet():
   """ Returns balance in the faucet """
   resp = requests.get("https://faucet.trtl.me/balance")
   desc = "```Donations: TRTLv14M1Q9223QdWMmJyNeY8oMjXs5TGP9hDc3GJFsUVdXtaemn1mLKA25Hz9PLu89uvDafx9A93jW2i27E5Q3a7rn8P2fLuVA```"
   em = discord.Embed(title = "The faucet has {:,} TRTL left".format(int(float(resp.json()['available']))), description = desc)
   em.url = "https://faucet.trtl.me"
   await client.say(embed = em)

@client.command()
async def price(exchange=None):
    """ Returns price """
    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    coindata = requests.get("https://tradeogre.com/api/v1/ticker/BTC-TRTL")
    btc = requests.get("https://www.bitstamp.net/api/ticker/")
    try:
        to_json = coindata.json()
    except ValueError:
        err_embed.description = "The {} API is down".format(config['price_source'])
        await client.say(embed = err_embed)
        return
    coindata_embed = discord.Embed(title = "Current Price of TRTL: {}".format(config['price_source']), 
        url = config['price_endpoint'])
    coindata_embed.add_field(name="Low", value="{0:,.0f} sats".format(round(float(coindata.json()['low'])*100000000)), inline=True)
    coindata_embed.add_field(name="Current", value="{0:,.0f} sats".format(round(float(coindata.json()['price'])*100000000)), inline=True)
    coindata_embed.add_field(name="High", value="{0:,.0f} sats".format(round(float(coindata.json()['high'])*100000000)), inline=True)

    coindata_embed.add_field(name="{}-USD".format(config['symbol']), 
        value="${0:,.4f} USD".format(float(coindata.json()['price'])*float(btc.json()['last'])), inline=True)

    coindata_embed.add_field(name="Volume", value="{:,.2f} BTC".format(float(coindata.json()['volume'])), inline=True)
    coindata_embed.add_field(name="BTC-USD", value="${0:,.2f} USD".format(float(btc.json()['last'])), inline=True)
    await client.say(embed = coindata_embed)

@client.command()
async def mcap():
    """ Returns current marketcap """
    btc = requests.get("https://www.bitstamp.net/api/ticker/")
    supply = get_supply()
    trtl = requests.get("https://tradeogre.com/api/v1/ticker/BTC-TRTL")
    try:
        trtl_json = trtl.json()
        btc_json = btc.json()
    except ValueError:
        await client.say("Unable to get market cap!")
        return
    mcap = float(trtl.json()['last'])*float(btc.json()['last'])*supply
    await client.say("{0}'s Marketcap is **${1:,.2f}** USD".format(config['coin'], mcap))


### NETWORK COMMANDS ###
@client.command()
async def hashrate():
    """ Returns network hashrate """
    data = daemon.getlastblockheader()
    hashrate = format_hash(float(data["block_header"]["difficulty"]) / 30)
    await client.say("The current global hashrate is **{:,.2f}/s**".format(hashrate))

@client.command()
async def difficulty():
    """ Returns network difficulty """
    data = daemon.getlastblockheader()
    difficulty = float(data["block_header"]["difficulty"])
    await client.say("The current difficulty is **{0:,.0f}**".format(difficulty))

@client.command()
async def height():
    """ Returns the current block count """
    await client.say("The current block height is **{:,}**".format(rpc.getStatus()['blockCount']))

@client.command()
async def supply():
    """ Returns the current circulating supply """
    supply = get_supply()
    await client.say("The current circulating supply is **{:0,.2f}** {}".format(supply, config['symbol']))


### WALLET COMMANDS ###
@client.command(pass_context = True)
async def registerwallet(ctx, address):
    " Register your wallet in the DB """
    address = address.strip()
    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    good_embed = discord.Embed(title="{}'s Wallet".format(ctx.message.author.name),colour=discord.Colour(0xD4AF37))
    if address == None:
        err_embed.description = "Please provide an address"
        await client.say(embed = err_embed)
        return

    exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
    addr_exists = session.query(Wallet).filter(Wallet.address == address).first()
    if exists:
        good_embed.title = "Your wallet exists!".format(exists.address)
        good_embed.description = "```{}``` use `{}updatewallet <addr>` to change".format(exists.address, config['prefix'])
        await client.say(embed = good_embed)
        return
    if addr_exists:
        err_embed.description = "Address already registered by another user!"
        await client.say(embed = err_embed)
        return

    elif not exists and len(address) == 99:
        w = Wallet(address,ctx.message.author.id,ctx.message.id)
        session.add(w)
        session.commit()
        good_embed.title = "Successfully registered your wallet"
        good_embed.description = "```{}```".format(address)
        await client.say(embed = good_embed)

        pid = gen_paymentid(address)
        balance = session.query(TipJar).filter(TipJar.paymentid == pid).first()
        if not balance:
            t = TipJar(pid, ctx.message.author.id, 0)
            session.add(t)
        else:
            balance.paymentid = pid
        session.commit()
        tipjar_addr = rpc.getAddresses()['addresses'][0]
        good_embed.title = "Your Tipjar Info"
        good_embed.description = "Deposit TRTL to start tipping! ```transfer 3 {} <amount> -p {}```".format(tipjar_addr, pid)
        balance = session.query(TipJar).filter(TipJar.paymentid == pid).first()
        await client.send_message(ctx.message.author, embed = good_embed)
        return
    elif len(address) > 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too long"
    elif len(address) < 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too short"
    await client.say(embed = err_embed)

@client.command(pass_context = True)
async def updatewallet(ctx, address):
    """ Updates your wallet address """
    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))

    if address == None:
        err_embed.description = "Please provide an address"
        await client.say(embed = err_embed)
        return

    address = address.strip()
    good_embed = discord.Embed(title="{}'s Updated Wallet".format(ctx.message.author.name),colour=discord.Colour(0xD4AF37))
    exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
    if not exists:
        err_embed.description = "You haven't registered a wallet!"

    addr_exists = session.query(Wallet).filter(Wallet.address == address).first()
    if addr_exists:
        err_embed.description = "Address already registered by another user!"
        await client.say(embed = err_embed)
        return
    elif exists and len(address) == 99:
        old_pid = gen_paymentid(exists.address)
        old_balance = session.query(TipJar).filter(TipJar.paymentid == old_pid).first()
        exists.address = address
        session.commit()
        good_embed.title = "Successfully updated your wallet"
        good_embed.description = "```{}```".format(address)
        await client.say(embed = good_embed)

        pid = gen_paymentid(address)
        balance = session.query(TipJar).filter(TipJar.paymentid == pid).first()
        if not balance:
            t = TipJar(pid, ctx.message.author.id, 0)
            session.add(t)
        else:
            balance.paymentid = pid
            balance.amount += old_balance.amount
        tipjar_addr = rpc.getAddresses()['addresses'][0]
        good_embed.title = "Your Tipjar Info"
        good_embed.description = "Deposit TRTL to start tipping! ```transfer 3 {} <amount> -p {}```".format(tipjar_addr, pid)
        session.commit()
        await client.send_message(ctx.message.author, embed = good_embed)
        good_embed.title = "Balance Update"
        good_embed.description = "New Balance: `{:0,.2f}` {}".format(balance.amount / config['units'], config['symbol'])
        await client.send_message(ctx.message.author, embed = good_embed)
        return
    elif len(address) > 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too long"
    elif len(address) < 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too short"
    await client.say(embed = err_embed)

@client.command(pass_context = True)
async def wallet(ctx, user: discord.User=None):
    """ Returns specified user's wallet address or your own if None """
    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    good_embed = discord.Embed(colour=discord.Colour(0xD4AF37))
    if not user:
        exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
        if not exists:
            err_embed.description = "You haven't registered a wallet or specified a user!"
        else:
            good_embed.title = "Your wallet"
            good_embed.description = "```{}```".format(exists.address)
            await client.say(embed = good_embed)
            return
    else:
        exists = session.query(Wallet).filter(Wallet.userid == user.id).first()
        if not exists:
            err_embed.description = "{} hasn't registered a wallet!".format(user.name)
        else:
            good_embed.title = "{}'s wallet".format(user.name)
            good_embed.description = "```{}```".format(exists.address)
            await client.say(embed = good_embed)
            return
    await client.say(embed = err_embed)

@client.command(pass_context = True)
async def deposit(ctx, user: discord.User=None):
    """ PMs your deposit information for the tipjar """
    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    good_embed = discord.Embed(title="Your Tipjar Info")
    exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
    tipjar_addr = rpc.getAddresses()['addresses'][0]
    if exists:
        pid = gen_paymentid(exists.address)
        good_embed.description = "Deposit TRTL to start tipping! ```transfer 3 {} <amount> -p {}```".format(tipjar_addr, pid)
        balance = session.query(TipJar).filter(TipJar.paymentid == pid).first()
        if not balance:
            t = TipJar(pid, ctx.message.author.id, 0)
            session.add(t)
            session.commit()
        await client.send_message(ctx.message.author, embed = good_embed)
    else:
        err_embed.description = "You haven't registered a wallet!"
        err_embed.add_field(name="Help", value="Use `{}registerwallet <addr>` before trying to tip!".format(config['prefix']))
        await client.say(embed = err_embed)

@client.command(pass_context = True)
async def balance(ctx, user: discord.User=None):
    """ PMs your tipjar balance """
    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    good_embed = discord.Embed(title="Your Tipjar Balance is")
    exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
    if exists:
        pid = gen_paymentid(exists.address)
        balance = session.query(TipJar).filter(TipJar.paymentid == pid).first()
        if not balance:
            t = TipJar(pid, ctx.message.author.id, 0)
            session.add(t)
            session.commit()
        else:
            good_embed.description = "`{0:,.2f}` {1}".format(balance.amount / config['units'], config['symbol'])
            await client.send_message(ctx.message.author, embed = good_embed)
    else:
        err_embed.description = "You haven't registered a wallet!"
        err_embed.add_field(name="Help", value="Use `{}registerwallet <addr>` before trying to tip!".format(config['prefix']))
        await client.say(embed = err_embed)


@client.command(pass_context = True)
async def tip(ctx, amount, user: discord.User=None):
    """ Tips a user <amount> of coin """
    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    request_desc = "Register with `{}registerwallet <youraddress>` to get started!".format(config['prefix'])
    request_embed = discord.Embed(title="{} wants to tip you".format(ctx.message.author.mention),description=request_desc)
    good_embed = discord.Embed(title="You were tipped!",colour=discord.Colour(0xD4AF37))

    try:
        amount = int(round(float(amount)*config['units']))
    except:
        if user:
            await client.say("Amount must be a number > {}".format(1 / config['units']))
        else:
            await client.say("Usage: !tip <amount> @username")
        return
    if not user:
        await client.say("Usage: !tip <amount> @username")
        return

    if amount <= 1:
        err_embed.description = "`amount` must be greater than {}".format(1 / config['units'])
        await client.say(embed = err_embed)
        return

    if user.id == ctx.message.author.id:
        err_embed.description = "You cannot tip yourself!"
        await client.say(embed = err_embed)
        return

    user_exists = session.query(Wallet).filter(Wallet.userid == user.id).first()
    self_exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()


    if self_exists and user_exists:
        pid = gen_paymentid(self_exists.address)
        balance = session.query(TipJar).filter(TipJar.paymentid == pid).first()
        if not balance:
            t = TipJar(pid, ctx.message.author.id, 0)
            session.add(t)
            session.commit()
            err_embed.description = "You are now registered, please `!deposit` to tip"
            await client.send_message(ctx.message.author, embed = err_embed)

        else:
            fee = get_fee(amount)
            if balance.amount < 0:
                balance.amount = 0
                session.commit()
                err_embed.description = "Your balance was negative!"
                await client.send_message(ctx.message.author, embed=err_embed)
                return
            if amount + fee > balance.amount:
                err_embed.description = "Your balance is too low! Amount + Fee = `{}` {}".format((amount+fee) / config['units'], config['symbol'])
                await client.send_message(ctx.message.author, embed=err_embed)
                return
            else:
                transfer = build_transfer(user_exists.address, amount, self_exists.address, balance)
                print(transfer)
                result = rpc.sendTransaction(transfer)
                print(result)
                if (balance.amount - amount+fee) < 0:
                    print("ERROR! Balance corrupted")
                    balance.amount = 0
                    return
                try:
                    session.commit()
                except:
                    session.rollback()
                    raise
                await client.add_reaction(ctx.message, "\U0001F4B8")
                await client.send_message(ctx.message.author, "Sent `{0:,.2f}` {1}".format(amount / config['units'], config['symbol']))
                good_embed.description = "{0} sent you `{1:,.2f}` {2} with Transaction Hash ```{3}```".format(ctx.message.author.mention, amount / config['units'], config['symbol'],
                    result['transactionHash'])

                good_embed.url = "https://blocks.turtle.link/?hash={}#blockchain_transaction".format(result['transactionHash'])
                await client.send_message(user, embed = good_embed)

                balance.amount -= amount+fee
                tx = Transaction(result['transactionHash'])
                session.add(tx)
                session.commit()
                good_embed.title = "Balance Update"
                good_embed.description = "New Balance: `{:0,.2f}` {}".format(balance.amount / config['units'], config['symbol'])
                await client.send_message(ctx.message.author, embed = good_embed)
                return
    elif amount > int(rpc.getBalance()['availableBalance']):
        err_embed.description = "Too many coins are locked, please wait."
    elif not user_exists:
        err_embed.description = "{} hasn't registered to be tipped!".format(user.name)
        await client.send_message(user, embed = request_embed)
    else:
        err_embed.description = "You haven't registered a wallet!"
        err_embed.add_field(name="Help", value="Use `{}registerwallet <addr>` before trying to tip!".format(config['prefix']))
    await client.say(embed = err_embed)

client.run(config['token'])
