from poke_env.environment.battle import Battle
from poke_env.player.battle_order import BattleOrder
from poke_env import AccountConfiguration, ShowdownServerConfiguration
from poke_env.player.player import Player
from poke_env.environment.move import Move
from poke_env.environment.pokemon import Pokemon
import pandas as pd
from typing import List
import logging


def find_move_effect(move_name: str, move_effects: pd.DataFrame):
    move_effect = move_effects.loc[move_effects["name"] == move_name]
    if move_effect.empty:
        return None
    # tf is this
    return list(move_effect.to_dict()["effect"].values())[0]


class ShowdownSinglePlayer(Player):
    def __init__(
        self,
        account_configuration: AccountConfiguration,
        server_configuration: ShowdownServerConfiguration,
    ):
        self.move_effects = pd.read_csv("data/moves.csv")
        super().__init__(
            account_configuration=account_configuration,
            server_configuration=server_configuration,
            save_replays=True,
        )

    async def _handle_battle_message(self, split_messages: List[List[str]]):
        battle_log = []
        for event in split_messages:
            message = "|".join(event)
            if (
                message.startswith("|request")
                or message.startswith(">")
                or message.startswith("|upkeep")
                or message.startswith("|t:|")
            ):
                continue
            battle_log.append(message)
        with open("battle_log.txt", "a") as f:
            f.write("\n".join(battle_log))

        await super()._handle_battle_message(split_messages)

    def _get_team_data(self, battle: Battle, opponent: bool = False) -> dict:
        result = {}
        if not opponent:
            team = battle.team
        else:
            team = battle.opponent_team
        for pokemon in team.values():
            result[pokemon.species] = {
                "moves": {},
                "hp": pokemon.current_hp,
                "ability": pokemon.ability,
                "fainted": pokemon.fainted,
                "item": pokemon.item,
                "tera": pokemon.tera_type if pokemon.terastallized else "",
                "name": pokemon.species,
                "boosts": pokemon.boosts,
                "level": pokemon.level,
            }
            for move in pokemon.moves.keys():
                result[pokemon.species]["moves"][pokemon.moves[move].entry["name"]] = {
                    "type": pokemon.moves[move].entry["type"],
                    "accuracy": pokemon.moves[move].entry["accuracy"],
                    "secondary effect": pokemon.moves[move].entry["secondary"],
                    "base power": pokemon.moves[move].entry["basePower"],
                    "category": pokemon.moves[move].entry["category"],
                    "priority": pokemon.moves[move].entry["priority"],
                    "effect": find_move_effect(
                        pokemon.moves[move].entry["name"], self.move_effects
                    ),
                }
        return result

    def choose_move(self, battle: Battle) -> BattleOrder:

        player_team = self._get_team_data(battle)

        print("PLAYER TEAM")
        print(player_team)

        opponent_team = self._get_team_data(battle, opponent=True)

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

        moves_available = [
            battle_order.order
            for battle_order in available_orders
            if isinstance(battle_order.order, Move)
        ]
        pokemon_available = [
            battle_order.order
            for battle_order in available_orders
            if isinstance(battle_order.order, Pokemon)
        ]

        return self.choose_random_move(battle)
