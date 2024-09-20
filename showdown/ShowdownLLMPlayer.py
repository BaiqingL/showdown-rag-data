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
from unsloth import FastLanguageModel
from transformers import TextStreamer

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
        super().__init__(
            account_configuration=account_configuration,
            server_configuration=server_configuration,
            save_replays=True,
            start_timer_on_battle_start=False,
            battle_format="gen9randombattle",
        )
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name = "showdown/lora_model",
            max_seq_length = 10240,
            dtype = None,
            load_in_4bit = True,
        )
        FastLanguageModel.for_inference(self.model)
        self.text_streamer = TextStreamer(self.tokenizer)


    def _contact_llm(self, message: str):
        msg_format = "user\n{}<|im_end|>\n<|im_start|>\nassistant\n".format(message)
        inputs = self.tokenizer([msg_format], return_tensors = "pt").to("cuda")

        output = self.model.generate(**inputs, streamer = self.text_streamer, max_new_tokens = 2048)
        generated_token_ids = output[0][len(inputs['input_ids'][0]):]
        generated_text = self.tokenizer.decode(generated_token_ids, skip_special_tokens=True)

        return generated_text

    def _generate_prompt(
        self,
        game_history,
        player_team,
        opponent_team,
        player_moves_impact,
        opponent_moves_impact,
        player_active,
        opponent_active,
        available_choices,
    ) -> str:

        type_effectiveness_prompt = """
Type      | Strong Against         | Weak To
----------|------------------------|------------------
Normal    | -                      | Fighting
Fire      | Grass, Ice, Bug, Steel | Water, Ground, Rock
Water     | Fire, Ground, Rock     | Electric, Grass
Electric  | Water, Flying          | Ground
Grass     | Water, Ground, Rock    | Fire, Ice, Poison, Flying, Bug
Ice       | Grass, Ground, Flying, | Fire, Fighting, Rock, Steel
          | Dragon                 |
Fighting  | Normal, Ice, Rock,     | Flying, Psychic, Fairy
          | Dark, Steel            |
Poison    | Grass, Fairy           | Ground, Psychic
Ground    | Fire, Electric, Poison,| Water, Grass, Ice
          | Rock, Steel            |
Flying    | Grass, Fighting, Bug   | Electric, Ice, Rock
Psychic   | Fighting, Poison       | Bug, Ghost, Dark
Bug       | Grass, Psychic, Dark   | Fire, Flying, Rock
Rock      | Fire, Ice, Flying, Bug | Water, Grass, Fighting, Ground, Steel
Ghost     | Psychic, Ghost         | Ghost, Dark
Dragon    | Dragon                 | Ice, Dragon, Fairy
Dark      | Psychic, Ghost         | Fighting, Bug, Fairy
Steel     | Ice, Rock, Fairy       | Fire, Fighting, Ground
Fairy     | Fighting, Dragon, Dark | Poison, Steel
"""
        prompt_template = """You are an expert in Pokemon and competitive battling. Right now you are in a battle of the format random battles using Pokemon up to generation 9.

Here's the scenario:
[SCENARIO]

Start with a brief overview of the situation.
Break down your reasoning step-by-step, and be thorough in your analysis. Provide reasoning in sections.

Make sure to cite the tips you used when making your decision.

Consider type advantages, the alternative moves the player could have made and why they might have been rejected.
Conclude with a summary of why this move was likely the best choice in this situation.

Here's the type effectiveness chart:
[TYPE EFFECTIVENESS CHART]

Your current team and moves as to the best of your knowledge:

[PLAYER_TEAM_INFO]

The opponent team and moves as to the best of your knowledge, since I also looked up the potential movesets for you:

[OPPONENT_TEAM_INFO]

Here is the impact of the your [PLAYER_POKEMON]'s moves and the hp range that the move will do:
[PLAYER_MOVES_IMPACT]

Here is the impact of the opponent's [OPPONENT_POKEMON] moves and the hp range that the move will do:
[OPPONENT_MOVES_IMPACT]

Your [PLAYER_POKEMON]. You have the following choices:
[CHOICES]

Format your response in the following way:

<Summary>

<Analysis>

<Conclusion>

<Choice>

Finally, end your response with the choice, in the format of "Final choice: [choice number]"""

        return (
            prompt_template.replace("[SCENARIO]", game_history)
            .replace("[TYPE EFFECTIVENESS CHART]", type_effectiveness_prompt)
            .replace("[PLAYER_TEAM_INFO]", player_team)
            .replace("[OPPONENT_TEAM_INFO]", opponent_team)
            .replace("[PLAYER_MOVES_IMPACT]", player_moves_impact)
            .replace("[OPPONENT_MOVES_IMPACT]", opponent_moves_impact)
            .replace("[PLAYER_POKEMON]", player_active)
            .replace("[OPPONENT_POKEMON]", opponent_active)
            .replace("[CHOICES]", available_choices)
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

    def _calculate_damage(
        self,
        atkr: dict,
        defdr: dict,
        move_used,
        opponent: bool = False,
        log: bool = False,
    ):

        # remove key evasion and accuracy from boosts
        if "evasion" in atkr["boosts"]:
            del atkr["boosts"]["evasion"]
        if "accuracy" in atkr["boosts"]:
            del atkr["boosts"]["accuracy"]
        if "evasion" in defdr["boosts"]:
            del defdr["boosts"]["evasion"]
        if "accuracy" in defdr["boosts"]:
            del defdr["boosts"]["accuracy"]
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
        if log:
            print("Attacker: ", attacker)
            print("Defender: ", defender)
            print("Defender HP: ", defender.originalCurHP)
            print("Move: ", move)
            print("RESULT: ", result)
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
        if log:
            print("DEFENDER HP Ratio: ", hp)
            print("MIN DMG: ", min_dmg)
            print("MAX DMG: ", max_dmg)
            print("MOVE USED: ", move_used)
        if hp == 0:
            return "100%", "100%"
        if hp == None:
            hp = defdr.get("maximum hp")
        if opponent:
            min_dmg_percent = int(
                min_dmg / (defender.originalCurHP * (hp / 100.0)) * 100
            )
            max_dmg_percent = int(
                max_dmg / (defender.originalCurHP * (hp / 100.0)) * 100
            )
        else:
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
                (
                    move,
                    self._calculate_damage(
                        cur_player_side, cur_opponent_side, move, opponent=True
                    ),
                )
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
                str(i+1)
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
            cur_player_side["name"],
            cur_opponent_side["name"],
            available_orders_prompt,
        )

        if not self.random_strategy:
            choice = self._contact_llm(prompt)
            choice = choice.lower().split("final choice:")[1]
            choice = "".join(filter(str.isdigit, choice)).strip()
            print("CHOICE: ", choice)
            if choice == "" or int(choice) >= len(available_orders):
                print("Unable to parse choice, choosing randomly")
                # randomly choose cuz we got nothing lol
                return available_orders[int(random.random() * len(available_orders))]

            # compensate for 0th index
            choice = int(choice) - 1

            return available_orders[choice]
        else:
            return available_orders[int(random.random() * len(available_orders))]