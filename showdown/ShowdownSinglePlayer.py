from poke_env.environment.battle import Battle
from poke_env.player.battle_order import BattleOrder
from poke_env import AccountConfiguration, ShowdownServerConfiguration
from poke_env.player.player import Player
from poke_env.environment.move import Move
from poke_env.environment.pokemon import Pokemon

from typing import List
import logging


class ShowdownSinglePlayer(Player):
    def __init__(
        self,
        account_configuration: AccountConfiguration,
        server_configuration: ShowdownServerConfiguration,
    ):
        super().__init__(
            account_configuration=account_configuration,
            server_configuration=server_configuration,
            save_replays=True,
        )

    async def _handle_battle_message(self, split_messages: List[List[str]]):
        battle_log = []
        for event in split_messages:
            message = "|".join(event)
            if message.startswith("|request") or message.startswith(">") or message.startswith("|upkeep") or message.startswith("|t:|"):
                continue
            battle_log.append(message)
        with open("battle_log.txt", "a") as f:
            f.write("\n".join(battle_log))

        await super()._handle_battle_message(split_messages)

    def choose_move(self, battle: Battle) -> BattleOrder:

        available_orders = [BattleOrder(move) for move in battle.available_moves]
        available_orders.extend(
            [BattleOrder(switch) for switch in battle.available_switches]
        )

        if battle.can_mega_evolve:
            available_orders.extend(
                [BattleOrder(move, mega=True) for move in battle.available_moves]
            )

        if battle.can_dynamax:
            available_orders.extend(
                [BattleOrder(move, dynamax=True) for move in battle.available_moves]
            )

        if battle.can_tera:
            available_orders.extend(
                [
                    BattleOrder(move, terastallize=True)
                    for move in battle.available_moves
                ]
            )

        if battle.can_z_move and battle.active_pokemon:
            available_z_moves = set(battle.active_pokemon.available_z_moves)
            available_orders.extend(
                [
                    BattleOrder(move, z_move=True)
                    for move in battle.available_moves
                    if move in available_z_moves
                ]
            )

        moves_available = [battle_order.order for battle_order in available_orders if isinstance(battle_order.order, Move)]
        pokemon_available = [battle_order.order for battle_order in available_orders if isinstance(battle_order.order, Pokemon)]
        print(moves_available)
        print(pokemon_available)


        return self.choose_random_move(battle)
