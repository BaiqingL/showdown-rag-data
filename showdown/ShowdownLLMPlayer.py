from poke_env.environment.battle import Battle
from poke_env.player.battle_order import BattleOrder
from poke_env import AccountConfiguration, ShowdownServerConfiguration
from poke_env.player.player import Player
from poke_env.environment.move import Move
from poke_env.environment.pokemon import Pokemon
import pandas as pd
from typing import List
import requests, copy, logging, os, re, json, random
from javascript import require
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

OPENAI_ORG_ID = os.getenv("OPENAI_ORG_ID")
OPENAI_PROJECT_ID = os.getenv("OPENAI_PROJECT_ID")
OPENAI_SECRET_KEY = os.getenv("OPENAI_SECRET_KEY")


class ShowdownLLMPlayer(Player):
    def __init__(
        self,
        account_configuration: AccountConfiguration,
        server_configuration: ShowdownServerConfiguration,
        random_strategy: bool = False,
    ):
        self.random_strategy = random_strategy
        self.random_sets = requests.get(
            "https://pkmn.github.io/randbats/data/gen9randombattle.json"
        ).json()
        self.random_sets = {k.lower(): v for k, v in self.random_sets.items()}
        self.move_effects = pd.read_csv("data/moves.csv")
        self.item_lookup = json.load(open("data/items.json"))
        self.game_history = []
        self.llm_client = OpenAI(
            organization=OPENAI_ORG_ID,
            project=OPENAI_PROJECT_ID,
            api_key=OPENAI_SECRET_KEY,
        )
        super().__init__(
            account_configuration=account_configuration,
            server_configuration=server_configuration,
            save_replays=True,
            start_timer_on_battle_start=False,
            battle_format="gen9randombattle",
        )

    def _contact_llm(self, message: str):
        response = self.llm_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": message}],
            stream=False,
        )
        choice = response.choices[0].message.content
        print(choice)
        # grab the last line from choice
        choice = choice.split("\n")[-1]
        return choice

    def _generate_prompt(
        self,
        game_history,
        player_team,
        opponent_team,
        player_moves_impact,
        opponent_moves_impact,
        opponent_moves_impact_team,
        player_active,
        opponent_active,
        available_choices,
        fainted=False,
    ) -> str:
        prompt_not_fainted = """You are an expert in Pokemon and competitive battling. You are the best Pokemon showdown player in the random battle format.
You have been invited to a Pokemon tournament with a grand prize of $1,000,000. You are confident that you will win the tournament.
You're skills are the best in the world, and you have never lost a random battle in your life. You are the best of the best.
You know when to switch, when to set up, and when to attack. You know the best moves to use in every situation.

Below is information about your team, what you currently know about the opponent team, and the current history of the battle.

Here is the current history of the battle:

GAME_HISTORY

Your current team and moves as to the best of your knowledge:

PLAYER_TEAM_INFO

The opponent team and moves as to the best of your knowledge, since I also looked up the potential movesets for you:

OPPONENT_TEAM_INFO

Given that you currently have sent out PLAYER_POKEMON as your pokemon and the opponent has sent out OPPONENT_POKEMON, here is what your moves can probably do to the opponent in terms of hp ranges:

PLAYER_MOVES_IMPACT

However, given the potential moves the opponent has, here is what the opponent can do to you in terms of hp ranges:

OPPONENT_MOVES_IMPACT_INDIVIDUAL

This is also what the opponent moves can do to the rest of your team, if you decide to switch, if you are ineffective against the opponent or obviously weak against the opponent, switch out!

OPPONENT_MOVES_IMPACT_TEAM

Again, right now your pokemon is PLAYER_POKEMON and the opponent pokemon is OPPONENT_POKEMON.

Here are the available choices you can make:

AVAILABLE_CHOICES

Setting up is important, and you know when to switch, when to set up, and when to attack. Sometimes it's good to sacrifice a pokemon to get a free switch in, and sometimes it's good to set up to sweep the opponent's team. You know the best moves to use in every situation.

Give the reasoning for the move, consider what the enemy may want to do, what you may want to do, what setups are important, and consider type advantage and switching in to tank potential hits.

However, end your response with the number, the final line you should respond with should look like: "Final choice: 0" where 0 is the number of the choice you want to make.
"""

        prompt_fainted = """You are an expert in Pokemon and competitive battling. You are the best Pokemon showdown player in the random battle format.
You have been invited to a Pokemon tournament with a grand prize of $1,000,000. You are confident that you will win the tournament.
You're skills are the best in the world, and you have never lost a random battle in your life. You are the best of the best.
You know when to switch, when to set up, and when to attack. You know the best moves to use in every situation.

Below is information about your team, what you currently know about the opponent team, and the current history of the battle.

Here is the current history of the battle:

GAME_HISTORY

Note that the pokemon PLAYER_POKEMON you sent out has fainted, and you need to switch to another pokemon.

Your current team and moves as to the best of your knowledge:

PLAYER_TEAM_INFO

The opponent team and moves as to the best of your knowledge, since I also looked up the potential movesets for you:

OPPONENT_TEAM_INFO

This is what the opponent moves can probably do to the rest of your team given the current situation:

OPPONENT_MOVES_IMPACT_TEAM

Your Pokemon PLAYER_POKEMON has fainted, and the opponent currently has OPPONENT_POKEMON out.

Here are the available switches you can make:

AVAILABLE_CHOICES

Don't swap something in that's weak to the opponent given the moves and types you know about them.

Give the reasoning for the move, consider what the enemy may want to do, what you may want to do, what setups are important, and consider type advantage and switching in to tank potential hits.

However, end your response with the number, the final line you should respond with should look like: "Final choice: 0" where 0 is the number of the choice you want to make.
"""
        if fainted:
            return (
                prompt_fainted.replace("GAME_HISTORY", game_history)
                .replace("PLAYER_TEAM_INFO", player_team)
                .replace("OPPONENT_TEAM_INFO", opponent_team)
                .replace("OPPONENT_MOVES_IMPACT_TEAM", opponent_moves_impact_team)
                .replace("PLAYER_POKEMON", player_active)
                .replace("OPPONENT_POKEMON", opponent_active)
                .replace("AVAILABLE_CHOICES", available_choices)
            )
        else:
            return (
                prompt_not_fainted.replace("GAME_HISTORY", game_history)
                .replace("PLAYER_TEAM_INFO", player_team)
                .replace("OPPONENT_TEAM_INFO", opponent_team)
                .replace("PLAYER_MOVES_IMPACT", player_moves_impact)
                .replace("OPPONENT_MOVES_IMPACT_INDIVIDUAL", opponent_moves_impact)
                .replace("OPPONENT_MOVES_IMPACT_TEAM", opponent_moves_impact_team)
                .replace("PLAYER_POKEMON", player_active)
                .replace("OPPONENT_POKEMON", opponent_active)
                .replace("AVAILABLE_CHOICES", available_choices)
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
        self.game_history.append("\n".join(battle_log))

        await super()._handle_battle_message(split_messages)

    def _find_move_effect(self, move_name: str, move_effects: pd.DataFrame):
        move_effect = move_effects.loc[move_effects["name"] == move_name]
        if move_effect.empty:
            return None
        # tf is this
        return list(move_effect.to_dict()["effect"].values())[0]

    def _find_potential_random_set(self, team_data):
        for pokemon in team_data.keys():
            pokemon_name = team_data[pokemon]["name"].strip().lower()
            if pokemon_name in self.random_sets.keys():
                known_moves = team_data[pokemon]["moves"]
                possible_sets = self.random_sets[pokemon_name]["roles"]
                for role in possible_sets:
                    if isinstance(known_moves, dict):
                        known_moves = set(known_moves.keys())
                    if known_moves.issubset(possible_sets[role]["moves"]):
                        # also grab the evs and ivs for the pokemon
                        if "evs" in possible_sets[role]:
                            team_data[pokemon]["evs"] = possible_sets[role]["evs"]
                        if "ivs" in possible_sets[role]:
                            team_data[pokemon]["ivs"] = possible_sets[role]["ivs"]

                        potential_moveset = possible_sets[role]["moves"]
                        seen_unseen_moves = dict()
                        for move in potential_moveset:
                            if move in known_moves:
                                seen_unseen_moves[move] = "seen"
                            else:
                                seen_unseen_moves[move] = "unseen"
                        team_data[pokemon]["moves"] = seen_unseen_moves

                        break
        return team_data

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
                "item": self.item_lookup.get(pokemon.item, ""),
                "tera": (
                    pokemon.tera_type.name.lower().capitalize()
                    if pokemon.terastallized
                    else ""
                ),
                "name": pokemon._data.pokedex[pokemon.species]["name"],
                "boosts": pokemon.boosts,
                "level": pokemon.level,
            }
            for move in pokemon.moves.keys():
                result[pokemon.species]["moves"][pokemon.moves[move].entry["name"]] = {
                    "type": pokemon.moves[move].entry["type"],
                    "accuracy": pokemon.moves[move].entry["accuracy"],
                    "secondary effect": pokemon.moves[move].entry.get(
                        "secondary", None
                    ),
                    "base power": pokemon.moves[move].entry["basePower"],
                    "category": pokemon.moves[move].entry["category"],
                    "priority": pokemon.moves[move].entry["priority"],
                    "effect": self._find_move_effect(
                        pokemon.moves[move].entry["name"], self.move_effects
                    ),
                }
        return result

    def _calculate_damage(self, atkr: dict, defdr: dict, move_used):
        damage_calc = require("@smogon/calc")
        generation = damage_calc.Generations.get(9)
        attacker = None
        defender = None
        atkr_attributes = {}
        if "level" in atkr:
            atkr_attributes["level"] = atkr.get("level")
        if "item" in atkr:
            atkr_attributes["item"] = atkr.get("item")
        if "boosts" in atkr:
            atkr_attributes["boosts"] = atkr.get("boosts")
        if "tera" in atkr:
            atkr_attributes["teraType"] = atkr.get("tera")
        if "item" in atkr:
            atkr_attributes["item"] = atkr.get("item")
        if "evs" in atkr:
            atkr_attributes["evs"] = atkr.get("evs")
        if "ivs" in atkr:
            atkr_attributes["ivs"] = atkr.get("ivs")
        defdr_attributes = {}
        if "level" in defdr:
            defdr_attributes["level"] = defdr.get("level")
        if "item" in defdr:
            defdr_attributes["item"] = defdr.get("item")
        if "boosts" in defdr:
            defdr_attributes["boosts"] = defdr.get("boosts")
        if "tera" in defdr:
            defdr_attributes["teraType"] = defdr.get("tera")
        if "item" in defdr:
            defdr_attributes["item"] = defdr.get("item")
        if "evs" in defdr:
            defdr_attributes["evs"] = defdr.get("evs")
        if "ivs" in defdr:
            defdr_attributes["ivs"] = defdr.get("ivs")
        try:
            attacker = damage_calc.Pokemon.new(
                generation, atkr.get("name"), atkr_attributes
            )
        except:
            attacker = damage_calc.Pokemon.new(
                generation, atkr.get("name").split("-")[0], atkr_attributes
            )
        try:
            defender = damage_calc.Pokemon.new(
                generation, defdr.get("name"), defdr_attributes
            )
        except:
            defender = damage_calc.Pokemon.new(
                generation, defdr.get("name").split("-")[0], defdr_attributes
            )
        move = damage_calc.Move.new(generation, move_used)
        result = damage_calc.calculate(generation, attacker, defender, move)
        if result.damage == 0:
            return 0, 0
        if isinstance(result.damage, str):
            return result.damage + "%", result.damage + "%"
        try:
            if isinstance(result.damage, int):
                min_dmg = result.damage
                max_dmg = result.damage
            else:
                dmg_range = result.damage.valueOf()

                min_dmg = min(dmg_range)
                max_dmg = max(dmg_range)
        except:
            print("INPUTS: ", atkr.get("name"), defdr.get("name"), move_used)
            print(atkr)
            print(defdr)
            print("ERROR: ", result.damage)
            print("DMG RANGE: ", dmg_range)

        # calculate the percentage of damage
        hp = defdr.get("hp")
        if hp == 0:
            return "100%", "100%"
        if hp == None:
            hp = defdr.get("maximum hp")
        min_dmg_percent = int(min_dmg / hp * 100)
        max_dmg_percent = int(max_dmg / hp * 100)
        return str(min_dmg_percent) + "%", str(max_dmg_percent) + "%"

    def _format_move_impact(self, move_name, impact_ranges, pkm_name) -> str:
        return (
            "The move "
            + move_name
            + " will deal between "
            + str(impact_ranges[0])
            + " and "
            + str(impact_ranges[1])
            + " damage to "
            + pkm_name
        )

    def choose_move(self, battle: Battle) -> BattleOrder:

        player_team = self._get_team_data(battle)

        opponent_team = self._find_potential_random_set(
            self._get_team_data(battle, opponent=True)
        )

        player_moves_impact = []

        cur_player_side = player_team[battle.active_pokemon.species]
        cur_opponent_side = opponent_team[battle.opponent_active_pokemon.species]
        for move in cur_player_side["moves"].keys():
            player_moves_impact.append(
                (move, self._calculate_damage(cur_player_side, cur_opponent_side, move))
            )

        player_moves_impact_prompt = ""
        for impact in player_moves_impact:
            player_moves_impact_prompt += (
                self._format_move_impact(
                    impact[0], impact[1], cur_opponent_side["name"]
                )
                + "\n"
            )

        opponent_moves_impact = []
        for move in cur_opponent_side["moves"].keys():
            opponent_moves_impact.append(
                (move, self._calculate_damage(cur_opponent_side, cur_player_side, move))
            )

        opponent_moves_impact_prompt = ""
        for impact in opponent_moves_impact:
            opponent_moves_impact_prompt += (
                self._format_move_impact(impact[0], impact[1], cur_player_side["name"])
                + "\n"
            )

        opponent_moves_impact_team = {}
        for pokemon in player_team.keys():
            opponent_moves_impact_team[pokemon] = []
            for move in cur_opponent_side["moves"].keys():
                opponent_moves_impact_team[pokemon].append(
                    (
                        move,
                        self._calculate_damage(
                            player_team[pokemon], cur_opponent_side, move
                        ),
                    )
                )

        opponent_moves_impact_team_prompt = ""
        for pokemon in opponent_moves_impact_team.keys():
            for impact in opponent_moves_impact_team[pokemon]:
                opponent_moves_impact_team_prompt += (
                    self._format_move_impact(
                        impact[0], impact[1], player_team[pokemon]["name"]
                    )
                    + "\n"
                )

        available_orders: List[BattleOrder] = [
            BattleOrder(move) for move in battle.available_moves
        ]
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

        available_orders_prompt = ""
        for i in range(len(available_orders)):
            available_orders_prompt += (
                str(i)
                + ". "
                + str(available_orders[i]).replace("/choose", "").strip()
                + "\n"
            )

        game_history = "\n".join(self.game_history)
        prompt = self._generate_prompt(
            game_history,
            str(player_team),
            str(opponent_team),
            player_moves_impact_prompt,
            opponent_moves_impact_prompt,
            opponent_moves_impact_team_prompt,
            cur_player_side["name"],
            cur_opponent_side["name"],
            available_orders_prompt,
            battle.active_pokemon.fainted,
        )

        if not self.random_strategy:
            choice = self._contact_llm(prompt)
            choice = "".join(filter(str.isdigit, choice))
            if choice == "":
                # randomly choose cuz we got nothing lol
                return available_orders[int(random.random() * len(available_orders))]

            choice = int(choice)

            return available_orders[choice]
        else:
            return available_orders[int(random.random() * len(available_orders))]
