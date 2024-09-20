import asyncio, os

from poke_env import AccountConfiguration, ShowdownServerConfiguration
from ShowdownLLMPlayer import ShowdownLLMPlayer
from dotenv import load_dotenv

load_dotenv()
ACCT_PASSWORD = os.getenv("ACCT_PASSWORD")
INCOMING_USERNAME = os.getenv("INCOMING_USERNAME")


async def main():
    player = ShowdownLLMPlayer(
        account_configuration=AccountConfiguration("showdown-dojo", ACCT_PASSWORD),
        server_configuration=ShowdownServerConfiguration,
        random_strategy=False,
    )
    print("Logged in, ready to play")

    # await player.accept_challenges(INCOMING_USERNAME, 1)
    await player.ladder(1)


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
