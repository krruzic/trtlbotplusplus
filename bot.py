import asyncio

import discord
from discord.ext.commands import Bot, Context
import requests

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


from models import Wallet, TipJar, Base, Transaction
from utils import config, format_hash, gen_paymentid, rpc, daemon, \
        get_deposits, get_fee, build_transfer, get_supply, \
        reaction_tip_register, reaction_tipped_already

HEADERS = {'Content-Type': 'application/json'}

# SETUP ###
engine = create_engine('sqlite:///trtl.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()


client = Bot(
        description="{} Tipping Bot".format(config['symbol']),
        command_prefix=config['prefix'],
        pm_help=False)

async def wallet_watcher():
    await client.wait_until_ready()
    start = int(rpc.getStatus()['blockCount'])-10000
    while not client.is_closed:
        height = int(rpc.getStatus()['blockCount'])
        print("HEIGHT IS: " + str(height))
        for tx in get_deposits(start, session):
            session.add(tx)
            try:
                session.commit()
            except:
                session.rollback()
            balance = session.query(TipJar).filter(TipJar.paymentid == tx.paymentid).first()
            if not balance:  # don't do for withdrawal
                return

            good_embed = discord.Embed(title="Deposit Recieved!",colour=discord.Colour(0xD4AF37))
            good_embed.description = "Your deposit of {} {} has now been credited.".format(tx.amount/config['units'], config['symbol'])
            print("TRANSACTION PID IS: " + tx.paymentid)
            good_embed.add_field(name="New Balance", value="{0:,.2f}".format(balance.amount/config['units']))
            user = await client.get_user_info(str(balance.userid))
            await client.send_message(user, embed=good_embed)
        if start < height:
            start += 1000
        if start >= height:
            start = height-1
        await asyncio.sleep(0.5)  # just less than the block time

client.loop.create_task(wallet_watcher())


@client.event
async def on_ready():
    print("Bot online!")


# MARKET COMMANDS ###
@client.command()
async def faucet():
    """ Returns balance in the faucet """
    resp = requests.get("https://faucet.{}.me/balance".format(config['symbol']))
    desc = "```Donations: {}```".format(config['faucet'])
    em = discord.Embed(title = "The faucet has {:,} {} left".format(int(float(resp.json()['available'])), config['symbol']), description = desc)
    em.url = "https://faucet.{}.me".format(config['symbol'])
    await client.say(embed = em)


@client.command(pass_context=True)
async def price(ctx, exchange=None):
    """ Returns price (unusable in main Turtlecoin Discord) """
    try:
        if ctx.message.server.id == "388915017187328002":
            return
    except AttributeError as e:
        print(e)
        pass
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
    await client.say(embed=coindata_embed)


@client.command()
async def mcap():
    """ Returns current marketcap (unusable in main Turtlecoin Discord) """
    try:
        if ctx.message.server.id == "388915017187328002":
            return
    except:
        pass

    btc = requests.get("https://www.bitstamp.net/api/ticker/")
    supply = get_supply()
    trtl = requests.get("https://tradeogre.com/api/v1/ticker/BTC-TRTL")
    try:
        trtl_json = trtl.json()
        btc_json = btc.json()
    except ValueError:
        await client.say("Unable to get market cap!")
        return
    mcap = float(trtl.json()['price'])*float(btc.json()['last'])*supply
    await client.say("{0}'s Marketcap is **${1:,.2f}** USD".format(config['coin'], mcap))


### NETWORK COMMANDS ###
@client.command()
async def hashrate():
    """ Returns network hashrate """
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
    """ Returns the current block count """
    await client.say("The current block height is **{:,}**".format(rpc.getStatus()['blockCount']))


@client.command()
async def supply():
    """ Returns the current circulating supply """
    supply = get_supply()
    await client.say("The current circulating supply is **{:0,.2f}** {}".format(supply, config['symbol']))


# WALLET COMMANDS ###
@client.command(pass_context=True)
async def registerwallet(ctx, address):
    """ Register your wallet in the DB """
    wallet_channel = discord.utils.get(ctx.message.server.channels, name='wallets')
    if wallet_channel is None:
        wallet_channel = ctx.message.channel

    address = address.strip()
    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    good_embed = discord.Embed(title="{}'s Wallet".format(ctx.message.author.name),colour=discord.Colour(0xD4AF37))
    if address is None:
        err_embed.description = "Please provide an address"
        await client.send_message(ctx.message.author, embed = err_embed)
        return

    exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
    addr_exists = session.query(Wallet).filter(Wallet.address == address).first()
    if exists:
        good_embed.title = "Your wallet exists!".format(exists.address)
        good_embed.description = "```{}``` use `{}updatewallet <addr>` to change".format(exists.address, config['prefix'])
        await client.send_message(ctx.message.author, embed = good_embed)
        return
    if addr_exists:
        err_embed.description = "Address already registered by another user!"
        await client.send_message(ctx.message.author, embed = err_embed)
        return

    elif not exists and len(address) == 99:
        w = Wallet(address, ctx.message.author.id,ctx.message.id)
        session.add(w)
        session.commit()
        good_embed.title = "Successfully registered your wallet"
        good_embed.description = "```{}```".format(address)
        await client.send_message(ctx.message.author, embed = good_embed)

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
        good_embed.description = "Deposit {} to start tipping! ```transfer 3 {} <amount> -p {}```".format(config['symbol'], tipjar_addr, pid)
        balance = session.query(TipJar).filter(TipJar.paymentid == pid).first()
        await client.send_message(ctx.message.author, embed = good_embed)
        return
    elif len(address) > 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too long"
    elif len(address) < 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too short"
    await client.say(embed = err_embed)


@client.command(pass_context=True)
async def updatewallet(ctx, address):
    """ Updates your wallet address """
    wallet_channel = discord.utils.get(ctx.message.server.channels, name='wallets')
    if wallet_channel is None:
        wallet_channel = ctx.message.channel

    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))

    if address == None:
        err_embed.description = "Please provide an address!"
        await client.send_message(ctx.message.author, embed=err_embed)
        return

    address = address.strip()
    good_embed = discord.Embed(title="{}'s Updated Wallet".format(ctx.message.author.name),colour=discord.Colour(0xD4AF37))
    exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
    if not exists:
        err_embed.description = "You haven't registered a wallet!"

    addr_exists = session.query(Wallet).filter(Wallet.address == address).first()
    if addr_exists:
        err_embed.description = "Address already registered by another user!"
        await client.send_message(ctx.message.author, embed = err_embed)
        return
    elif exists and len(address) == 99:
        old_pid = gen_paymentid(exists.address)
        old_balance = session.query(TipJar).filter(TipJar.paymentid == old_pid).first()
        exists.address = address
        pid = gen_paymentid(address)
        old_balance.paymentid = pid
        good_embed.title = "Successfully updated your wallet"
        good_embed.description = "```{}```".format(address)
        session.commit()
        await client.send_message(ctx.message.author, embed = good_embed)

        tipjar_addr = rpc.getAddresses()['addresses'][0]
        good_embed.title = "Your Tipjar Info"
        good_embed.description = "Deposit {} to start tipping! ```transfer 3 {} <amount> -p {}```".format(config['symbol'], tipjar_addr, pid)
        await client.send_message(ctx.message.author, embed = good_embed)

        good_embed.title = "Balance Update"
        good_embed.url = ""
        good_embed.description = "New Balance: `{:0,.2f}` {}".format(balance.amount / config['units'], config['symbol'])
        await client.send_message(ctx.message.author, embed = good_embed)
        return
    elif len(address) > 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too long"
    elif len(address) < 99:
        err_embed.description = "Your wallet must be 99 characeters long, your entry was too short"
    await client.say(embed=err_embed)


@client.command(pass_context=True)
async def wallet(ctx, user: discord.User=None):
    """ Returns specified user's wallet address or your own if None """
    wallet_channel = discord.utils.get(ctx.message.server.channels, name='wallets')
    if wallet_channel is None:
        wallet_channel = ctx.message.channel

    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    good_embed = discord.Embed(colour=discord.Colour(0xD4AF37))
    if not user:
        exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
        if not exists:
            err_embed.description = "You haven't registered a wallet or specified a user!"
        else:
            good_embed.title = "Your wallet"
            good_embed.description = "Here's your wallet {}! ```{}```".format(ctx.message.author.mention, exists.address)
            await client.send_message(ctx.message.author, embed = good_embed)
            return
    else:
        exists = session.query(Wallet).filter(Wallet.userid == user.id).first()
        if not exists:
            err_embed.description = "{} hasn't registered a wallet!".format(user.name)
        else:
            good_embed.title = "{}'s wallet".format(user.name)
            good_embed.description = "```{}```".format(exists.address)
            await client.send_message(ctx.message.author, embed = good_embed)
            return
    await client.send_message(ctx.message.author, embed = err_embed)


@client.command(pass_context=True)
async def deposit(ctx, user: discord.User=None):
    """ PMs your deposit information for the tipjar """
    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    good_embed = discord.Embed(title="Your Tipjar Info")
    exists = session.query(Wallet).filter(Wallet.userid == ctx.message.author.id).first()
    tipjar_addr = rpc.getAddresses()['addresses'][0]
    if exists:
        pid = gen_paymentid(exists.address)
        good_embed.description = "Deposit {} to start tipping! ```transfer 3 {} <amount> -p {}```".format(config['symbol'], tipjar_addr, pid)
        balance = session.query(TipJar).filter(TipJar.paymentid == pid).first()
        if not balance:
            t = TipJar(pid, ctx.message.author.id, 0)
            session.add(t)
            session.commit()
        await client.send_message(ctx.message.author, embed = good_embed)
    else:
        err_embed.description = "You haven't registered a wallet!"
        err_embed.add_field(name="Help", value="Use `{}registerwallet <addr>` before trying to tip!".format(config['prefix']))
        await client.say(embed=err_embed)


@client.command(pass_context=True)
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
            await client.send_message(ctx.message.author, embed=good_embed)
    else:
        err_embed.description = "You haven't registered a wallet!"
        err_embed.add_field(name="Help", value="Use `{}registerwallet <addr>` before trying to tip!".format(config['prefix']))
        await client.say(embed=err_embed)


EMOJI_MONEYBAGS = "\U0001F4B8"
EMOJI_SOS = "\U0001F198"
EMOJI_ERROR = "\u274C"


@client.event
async def on_reaction_add(reaction, user):
    message = reaction.message
    mentions = message.mentions
    receiver = None

    if type(reaction.emoji) is str:
        # nobody cares about your basic emoji, discord.
        return

    if reaction_tipped_already(message, user):
        print("no duplicate amplifications / user already joined in")
        return

    if reaction.emoji.name == config['tip_amp_emoji']:
        # only tip with the right emoji (:tip: custom emoji by default)
        if not message.content.startswith("{}tip".format(config['prefix'])):
            # only tip on tip commands
            return

        if len(mentions) == 0 or message.author == user:
            print("no mentions / self double-tip / re-initial tip")
            # don't double-tip.
            return

        if EMOJI_MONEYBAGS not in [r.emoji for r in message.reactions]:
            # only amplify tip when the bot confirms with moneybags emoji
            return

        try:
            # extract the tip amount
            # .tip {amount} {tipees}
            message_amount = message.content.split(' ')[1]
            amount = int(round(float(message_amount))) # multiply by coin units in the actual tip command
        except:
            print("invalid tip message format ({})".format(message.content))
            return

        print("user {} joined tip!".format(user))
        await client.send_message(
                user,
                "You joined in the {} {} tip!".format(message_amount, config['symbol']))

    elif reaction.emoji.name == config['tip_any_emoji']:
        # tipping any message a static amount.
        amount = config['tip_any_amount']
        receiver = message.author

    else:
        # terminate, a custom emoji that we don't care about.
        return

    fake_ctx = Context(message=reaction.message, prefix=config['prefix'])
    success = await _tip(fake_ctx, amount, user, receiver)

    if success:
        # add user + message combo to tip cache.
        reaction_tip_register(message, user)


@client.command(pass_context=True)
async def tip(ctx, amount, sender):
    await _tip(ctx, amount, None, None)


async def _tip(ctx, amount,
               sender: discord.User=None,
               receiver: discord.User=None):
    """ Tips a user <amount> of coin """

    err_embed = discord.Embed(title=":x:Error:x:", colour=discord.Colour(0xf44242))
    good_embed = discord.Embed(title="You were tipped!", colour=discord.Colour(0xD4AF37))

    if not sender:  # regular tip
        sender = ctx.message.author

    if not receiver:
        tipees = ctx.message.mentions
    else:
        tipees = [receiver, ]

    try:
        amount = int(round(float(amount)*config['units']))
    except:
        await client.say("Amount must be a number > {}".format(10 / config['units']))
        return False

    if amount <= 10:
        err_embed.description = "`amount` must be greater than {}".format(10 / config['units'])
        await client.say(embed=err_embed)
        return False

    fee = get_fee(amount)
    self_exists = session.query(Wallet).filter(Wallet.userid == sender.id).first()

    if not self_exists:
        err_embed.description = "You haven't registered a wallet!"
        err_embed.add_field(name="Help", value="Use `{}registerwallet <addr>` before trying to tip!".format(config['prefix']))
        await client.say(embed=err_embed)
        return False

    pid = gen_paymentid(self_exists.address)
    balance = session.query(TipJar).filter(TipJar.paymentid == pid).first()
    if not balance:
        t = TipJar(pid, sender.id, 0)
        session.add(t)
        session.commit()
        err_embed.description = "You are now registered, please `{}deposit` to tip".format(config['prefix'])
        await client.send_message(sender, embed=err_embed)
        return False

    if balance.amount < 0:
        balance.amount = 0
        session.commit()
        err_embed.description = "Your balance was negative!"
        await client.send_message(sender, embed=err_embed)

        madk = discord.utils.get(client.get_all_members(), id='200823661928644617')
        err_embed.title = "{} had a negative balance!!".format(sender.name)
        err_embed.description = "PID: {}".format(pid)

        await client.send_message(madk, embed=err_embed)
        return False

    if ((len(tipees)*(amount))+fee) > balance.amount:
        err_embed.description = "Your balance is too low! Amount + Fee = `{}` {}".format(((len(tipees)*(amount))+fee) / config['units'], config['symbol'])
        await client.add_reaction(ctx.message, "\u274C")
        await client.send_message(sender, embed=err_embed)
        return False

    destinations = []
    actual_users = []
    failed = 0
    for user in tipees:
        user_exists = session.query(Wallet).filter(Wallet.userid == user.id).first()
        if user_exists:
            destinations.append({'amount': amount, 'address': user_exists.address})
            if user_exists.userid != sender.id:  # multitip shouldn't tip self.
                actual_users.append(user)
        else:
            print("user {} does not exist!!".format(user))

    if len(destinations) == 0:
        await client.add_reaction(ctx.message, EMOJI_SOS)
        return False

    transfer = build_transfer(amount, destinations, balance)
    print(transfer)
    result = rpc.sendTransaction(transfer)
    print(result)

    await client.add_reaction(ctx.message, EMOJI_MONEYBAGS)

    balance.amount -= ((len(actual_users)*amount)+fee)
    tx = Transaction(result['transactionHash'], (len(actual_users)*amount)+fee, balance.paymentid)
    session.add(tx)
    session.commit()
    good_embed.title = "Tip Sent!"
    good_embed.description = (
        "Sent `{0:,.2f}` {1} to {2} users! With Transaction Hash ```{3}```"
        .format(amount / config['units'],
                config['symbol'],
                len(actual_users),
                result['transactionHash']))
    good_embed.url = (
        "https://blocks.turtle.link/?hash={}#blockchain_transaction"
        .format(result['transactionHash']))

    good_embed.add_field(name="New Balance", value="`{:0,.2f}` {}".format(balance.amount / config['units'], config['symbol']))
    good_embed.add_field(name="Transfer Info", value="Successfully sent to {0} users. {1} failed.".format(len(actual_users), failed))
    await client.send_message(sender, embed=good_embed)

    for user in actual_users:
        good_embed = discord.Embed(title="You were tipped!", colour=discord.Colour(0xD4AF37))
        good_embed.description = (
            "{0} sent you `{1:,.2f}` {2} with Transaction Hash ```{3}```"
            .format(sender.mention,
                    amount / config['units'],
                    config['symbol'],
                    result['transactionHash']))
        good_embed.url = (
            "https://blocks.turtle.link/?hash={}#blockchain_transaction"
            .format(result['transactionHash']))

        await client.send_message(user, embed=good_embed)

    return True

client.run(config['token'])
