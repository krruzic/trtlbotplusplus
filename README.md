### Getting started with Turtlecoin
Make sure you have `walletd` and `TurtleCoind` running on the default ports and the blockexplorer enabled.
Install dependencies with `pip install -r requirements.txt` 

### Getting started with something else
This bot is currently very close to being generic enough to
work out of the box with any cryptonote coin. As of now a few changes will
be necessary however. 

0. Follow steps in previous section
1. Don't use the TrtlServer() class when connecting to the rpc. Just call `Server("your_rpc_url")` instead.
2. Make sure all the rpc calls are the same and send the same arguments. The spec is [here](https://wiki.bytecoin.org/wiki/Bytecoin_RPC_Wallet_JSON_RPC_API)
3. Price isn't going to work unless you modify the json references. Check your api spec!
4. The faucet command requires a very specific faucet right now. Set up [this](https://github.com/krruzic/turtlefaucet) first.

### Setting up config
Create a new file called `config.json` with the same structure as `config.json.example`.

Fill in the values with your information and you'll be ready to roll!

### Running the bot
`python3 bot.py`
