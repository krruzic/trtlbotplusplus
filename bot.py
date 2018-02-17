import asyncio
import os
import json

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
from utils import config, format_hash, gen_paymentid, rpc, daemon, get_deposits, get_fee, build_transfer

### SETUP ###
engine = create_engine('sqlite:///trtl.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()


async def wallet_watcher():
    await client.wait_until_ready()
    start = 194320
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
        await asyncio.sleep(10)


client = Bot(description="trtl bot for the trading channel", command_prefix=config['prefix'], pm_help = False)
client.loop.create_task(wallet_watcher())

@client.event
async def on_ready():
    print("Bot online!")


### MARKET COMMANDS ###
@client.command()
async def faucet():
    """ Returns TRTLs remaining in the faucet """
    resp = requests.get("https://faucet.trtl.me/balance")
    desc = "```Donations: TRTLv14M1Q9223QdWMmJyNeY8oMjXs5TGP9hDc3GJFsUVdXtaemn1mLKA25Hz9PLu89uvDafx9A93jW2i27E5Q3a7rn8P2fLuVA```"
    em = discord.Embed(title = "The faucet has {:,} TRTLs left".format(int(float(resp.json()['available']))), description = desc)
    em.url = "https://faucet.trtl.me"
    await client.say(embed = em)

@client.command()
async def price(exchange=None):
    """ Returns price on TradeOgre and TradeSatoshi """
    tradeogre = requests.get("https://tradeogre.com/api/v1/ticker/btc-trtl")
    btc = requests.get("https://www.bitstamp.net/api/ticker/")
    ogre_embed = discord.Embed(title = "Current Price of TRTL: Tradeogre", url = "https://tradeogre.com/exchange/BTC-TRTL")
    ogre_embed.add_field(name="Low", value="{0:,.0f} sats".format(round(float(tradeogre.json()['low'])*100000000)), inline=True)
    ogre_embed.add_field(name="Current", value="{0:,.0f} sats".format(round(float(tradeogre.json()['price'])*100000000)), inline=True)
    ogre_embed.add_field(name="High", value="{0:,.0f} sats".format(round(float(tradeogre.json()['high'])*100000000)), inline=True)
    ogre_embed.add_field(name="TRTL-USD", value="${0:,.5f} USD".format(float(tradeogre.json()['price'])*float(btc.json()['last'])), inline=True)
    ogre_embed.add_field(name="Volume", value="{0:,.2f} BTC".format(float(tradeogre.json()['volume'])), inline=True)
    ogre_embed.add_field(name="BTC-USD", value="${0:,.2f} USD".format(float(btc.json()['last'])), inline=True)
    tradesat = requests.get("https://tradesatoshi.com/api/public/getticker?market=TRTL_BTC")
    sat_embed = discord.Embed(title = "Current Price of TRTL: Trade Satoshi", url = "https://tradesatoshi.com/Exchange?market=TRTL_BTC")
    sat_embed.add_field(name="Bid", value="{0:,.0f} sats".format(round(float(tradesat.json()["result"]["bid"])*100000000)), inline=True)
    sat_embed.add_field(name="Ask", value="{0:,.0f} sats".format(round(float(tradesat.json()["result"]["ask"])*100000000)), inline=True)
    sat_embed.add_field(name="Last", value="{0:,.0f} sats".format(round(float(tradesat.json()["result"]["last"])*100000000)), inline=True) 
    sat_embed.add_field(name="TRTL-USD", value="${0:,.5f} USD".format(float(tradesat.json()["result"]["last"])*float(btc.json()['last'])), inline=True)
    sat_embed.add_field(name="BTC-USD", value="${0:,.2f} USD".format(float(btc.json()['last'])), inline=True)

    if not exchange:
        await client.say(embed = ogre_embed)
        await client.say(embed = sat_embed)
        return
    if str(exchange)=="all":
        await client.say(embed = ogre_embed)
        await client.say(embed = sat_embed)
        return
    if exchange in ["tradesat","tradesatoshi", "ts"]:
        await client.say(embed = sat_embed)

    elif exchange in ["tradeogre", "to"]:
        await client.say(embed = ogre_embed)

@client.command()
async def mcap():
    """ Returns current marketcap w/ TradeOgre data """
    trtl = requests.get("https://tradeogre.com/api/v1/ticker/btc-trtl")
    btc = requests.get("https://www.bitstamp.net/api/ticker/")
    supply = requests.get("https://blocks.turtle.link/q/supply/")
    mcap = float(trtl.json()['price'])*float(btc.json()['last'])*float(supply.text)
    await client.say("Turtlecoin's Marketcap is **${0:,.2f}** USD".format(mcap))


### NETWORK COMMANDS ###
@client.command()
async def hashrate():
    """ Returns Turtlecoin network hashrate """
    data = daemon.getlastblockheader()
    hashrate = format_hash(float(data["block_header"]["difficulty"]) / 30)
    await client.say("The current global hashrate is **{}/s**".format(hashrate))

@client.command()
async def difficulty():
    """ Returns network difficulty """
    data = daemon.getlastblockheader()
    difficulty = float(data["block_header"]["difficulty"])
    await client.say("The current difficulty is **{0:,.0f}**".format(difficulty))

@client.command()
async def height():
    """ Returns the current Turtlecoin block count """
    await client.say("The current block height is **{:,}**".format(rpc.getStatus()['blockCount']))

@client.command()
async def supply():
    """ Returns the current circulating supply of TRTLs """
    resp = requests.get("https://blocks.turtle.link/q/supply/")
    await client.say("The current circulating supply is **{:,}** TRTLs".format(int(float(resp.text))))


### SERVER COMMANDS ###
@client.command(pass_context = True)
async def exile(ctx, user: discord.User=None):
    """ Exiles specified user. Usable by MODs only """
    exile_role = discord.utils.get(ctx.message.server.roles,name='exiled')
    sender_roles = ctx.message.author.roles
    if not user:
        await client.say("Usage: !exile @username")
    for role in sender_roles:
        if role.name in ["MOD","ADMIN"]:
            await client.add_roles(user, exile_role)
            await client.say("Exiled {}!".format(user))
            return
    await client.say("You do not have permission to do that.")

@client.command(pass_context = True)
async def warn(ctx, user: discord.User=None):
    """ Marks specified user as WANTED. Usable by MODs only """
    exile_role = discord.utils.get(ctx.message.server.roles,name='WANTED')
    sender_roles = ctx.message.author.roles
    if not user:
        await client.say("Usage: !warn @username")
        return
    for role in sender_roles:
        if role.name in ["MOD","ADMIN"]:
            await client.add_roles(user, exile_role)
            await client.say("{} is now WANTED. This is a warning.".format(user))
            return
    await client.say("You do not have permission to do that.")

@client.command(pass_context = True)
async def free(ctx, user: discord.User=None):
    """ Frees exiled/wanted user. Usable by MODs only """
    exile_role = discord.utils.get(ctx.message.server.roles,name='exiled')
    wanted_role = discord.utils.get(ctx.message.server.roles,name='WANTED')
    sender_roles = ctx.message.author.roles
    if not user:
        await client.say("Usage: !free @username")
        return
    for role in sender_roles:
        if role.name in ["MOD","ADMIN"]:
            await client.remove_roles(user, exile_role)
            await client.say("{} is free!".format(user))
            return
    await client.say("You do not have permission to do that.")

@client.command(pass_context = True)
async def whine(ctx):
    """ Gives sender the whiner role """
    whiner_role = discord.utils.get(ctx.message.server.roles,name='whiner')
    await client.add_roles(ctx.message.author, whiner_role)
    await client.say("You are now a whiner!")


### WALLET COMMANDS ###
@client.command(pass_context = True)
async def registerwallet(ctx, address):
    " Register your wallet in the DB """
    address = address.strip()
    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    good_embed = discord.Embed(title="{}'s Wallet".format(ctx.message.author.name),colour=discord.Colour(0xD4AF37))
    if address == None:
        err_embed.description = "Please provide an address"
    exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
    if exists:
        good_embed.title = "Your wallet exists!".format(exists.address)
        good_embed.description = "```{}``` use `!updatewallet <addr>` to change".format(exists.address)
        await client.say(embed = good_embed)
        return
    elif not exists and len(address) == 99 and address.startswith("TRTL"):
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
            session.commit()
        else:
            balance.paymentid = pid
        return
    elif len(address) > 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too long"
    elif len(address) < 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too short"
    elif not address.startswith("TRTL"):
        err_embed.description = "Wallets start with `TRTL`"
    await client.say(embed = err_embed)

@client.command(pass_context = True)
async def updatewallet(ctx, address):
    """ Updates your wallet address """
    address = address.strip()
    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    good_embed = discord.Embed(title="{}'s Updated Wallet".format(ctx.message.author.name),colour=discord.Colour(0xD4AF37))
    exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
    if not exists:
        err_embed.description = "You haven't registered a wallet!"
    elif exists and len(address) == 99 and address.startswith("TRTL"):
        old_pid = gen_paymentid(exists.address)
        old_balance = session.query(TipJar).filter(TipJar.paymentid == old_pid).first()
        exists.address = address
        session.commit()
        good_embed.title = "Successfully updated your wallet"
        good_embed.description = "```{}```".format(address)
        await client.say(embed = good_embed)

        pid = gen_paymentid(exists.address)
        balance = session.query(TipJar).filter(TipJar.paymentid == pid).first()
        if not balance:
            t = TipJar(pid, ctx.message.author.id, 0)
            session.add(t)
            session.commit()
        else:
            balance.paymentid = pid
            balance.amount += old_balance.amount
        return
    elif len(address) > 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too long"
    elif len(address) < 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too short"
    elif not address.startswith("TRTL"):
        err_embed.description = "Wallets start with `TRTL`"
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
    await client.say(ember = err_embed)

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
        err_embed.add_field(name="Help", value="Use `!registerwallet <addr>` before trying to tip!")
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
            good_embed.description = "`{0:,.2f}` TRTLs".format(balance.amount / 100)
            await client.send_message(ctx.message.author, embed = good_embed)
    else:
        err_embed.description = "You haven't registered a wallet!"
        err_embed.add_field(name="Help", value="Use `!registerwallet <addr>` before trying to tip!")
        await client.say(embed = err_embed)

@client.command(pass_context = True)
async def tip(ctx, amount, user: discord.User=None):
    """ Tips a user <amount> TRTL """
    if not user:
        await client.say("Usage: !tip <amount> @username")

    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    request_desc = "Register with `!registerwallet TRTLyourwallet` to get started!"
    request_embed = discord.Embed(title="{} wants to tip you".format(ctx.message.author.mention),description=request_desc)
    good_embed = discord.Embed(title="You were tipped!",colour=discord.Colour(0xD4AF37))

    try:
        amount = int(round(float(amount)*100))
    except:
        if user:
            await client.say("Usage: !tip <amount> @username")
        else:
            await client.say("Usage: !tip <amount> @username")
    if amount <= 1:
        err_embed.description = "`amount` must be greater than 1"
        await client.say(ember = err_embed)
        return
    user_exists = session.query(Wallet).filter(Wallet.userid == user.id).first()
    self_exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
    if user.id == ctx.message.author.id:
        err_embed.description = "You cannot tip yourself!"
        await client.say(embed = err_embed)
        return
    if self_exists and amount < 50000000 and user_exists:
        pid = gen_paymentid(self_exists.address)
        balance = session.query(TipJar).filter(TipJar.paymentid == pid).first()
        print(balance)
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
                await client.send_message(ctx.message.author, "It has been reset to zero")
                return
            if amount + fee > balance.amount:
                err_embed.description = "Your balance is too low! Amount + Fee = `{}` TRTLs".format((amount+fee) / 100)
                await client.send_message(ctx.message.author, "You have `{0:,.2f}` TRTLs".format(balance.amount / 100))
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
                await client.say("Sent `{0:,.2f}` TRTLs".format(amount / 100))
                good_embed.description = "{} sent you `{}` TRTLs with Transaction Hash ```{}```".format(ctx.message.author.mention, amount / 100, result['transactionHash'])
                good_embed.url = "https://blocks.turtle.link/?hash={}#blockchain_transaction".format(result['transactionHash'])
                await client.send_message(user, embed = good_embed)

                balance.amount -= amount+fee
                tx = Transaction(result['transactionHash'])
                session.add(tx)
                session.commit()
                return
    elif amount > int(rpc.getBalance()['availableBalance']):
        err_embed.description = "Too many coins are locked, please wait."
    elif amount > 50000000:
        err_embed.description = "Transactions must be under 500k TRTLs!"
    elif not user_exists:
        err_embed.description = "{} hasn't registered to be tipped!".format(user.name)
        await client.send_message(user, embed = request_embed)
    else:
        err_embed.description = "You haven't registered a wallet!"
        err_embed.add_field(name="Help", value="Use `!registerwallet <addr>` before trying to tip!")
    await client.say(embed = err_embed)

@client.command(pass_context = True)
async def withdraw(ctx, address, amount=-1):
    #if amount == -1:
    pass
client.run(config['token'])
