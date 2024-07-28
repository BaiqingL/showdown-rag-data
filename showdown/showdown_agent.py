import asyncio

from poke_env import AccountConfiguration, ShowdownServerConfiguration
from ShowdownSinglePlayer import ShowdownSinglePlayer


async def main():
    player = ShowdownSinglePlayer(
        account_configuration=AccountConfiguration("showdown-dojo", "showdown-dojo"),
        server_configuration=ShowdownServerConfiguration,
    )
    await player.accept_challenges('viewerisland', 1)



if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())