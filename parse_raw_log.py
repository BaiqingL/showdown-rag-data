from javascript import require
from typing import List


def get_team_data(player_team: dict, side: str, turn_data):
    """
    Extracts and updates the team data based on the given turn data.

    Args:
        player_team (dict): A dictionary representing the player's team data.
        side (str): The side of the player ('winner' or 'loser').
        turn_data: The turn data to process.

    Returns:
        dict: The updated player's team data.

    """
    # turn data is one nested list in the log column field
    for event in turn_data:
        for action in event:
            split_action = action.split("|")
            # Detect new pokemon based on switch or drag
            if action.startswith("|switch|{}:".format(side)) or action.startswith(
                "|drag|{}:".format(side)
            ):
                # clear out the boosts of every pokemon
                for key in player_team.keys():
                    player_team[key]["boosts"] = {}
                pokemon_key = split_action[2].split(": ")[1]
                pokemon_data = split_action[3].split(", ")
                pokemon_name = pokemon_data[0]
                # print("KEY: {}, NAME: {}".format(pokemon_key, pokemon_name))
                hp = int(split_action[4].split("/")[0])
                if pokemon_key in player_team:
                    player_team[pokemon_key]["hp"] = hp
                    continue
                else:

                    player_team[pokemon_key] = {}
                    # create an empty moves set
                    player_team[pokemon_key]["moves"] = set()
                    # set hp
                    player_team[pokemon_key]["hp"] = hp
                    # set max hp
                    player_team[pokemon_key]["boosts"] = {}
                # set name
                player_team[pokemon_key]["name"] = pokemon_name
                maximum_hp = int(split_action[4].split("/")[1].split(" ")[0])
                player_team[pokemon_key]["maximum hp"] = maximum_hp
                # Remove the L from the level
                player_team[pokemon_key]["level"] = (
                    pokemon_data[1][1:] if len(pokemon_data) > 1 else None
                )
                # If gender is not specified, set it to None
                player_team[pokemon_key]["gender"] = (
                    pokemon_data[2] if len(pokemon_data) > 2 else None
                )

            elif action.startswith("|move|{}:".format(side)):
                # parse out the pokemon name, make sure to remove the player name, since the move is going to be formatted as player: move
                pokemon_key = split_action[2].split(": ")[1]
                move_name = split_action[3]
                player_team[pokemon_key]["moves"].add(move_name)
            elif action.startswith("|-boost|{}:".format(side)):
                boost_type = split_action[3]
                boost_amount = int(split_action[4])
                # Check if boost type is in the pokemon dictionary
                pokemon_key = split_action[2][2 + len(side) :]
                if boost_type in player_team[pokemon_key]["boosts"]:
                    player_team[pokemon_key]["boosts"][boost_type] += boost_amount
                else:
                    player_team[pokemon_key]["boosts"][boost_type] = boost_amount
            elif action.startswith("|-unboost|{}:".format(side)):
                # parse out the boost information
                boost_type = split_action[3]
                boost_amount = int(split_action[4])
                # Check if boost type is in the pokemon dictionary
                if boost_type in player_team[pokemon_key]["boosts"]:
                    player_team[pokemon_key]["boosts"][boost_type] -= boost_amount
                else:
                    player_team[pokemon_key]["boosts"][boost_type] = -boost_amount
            elif action.startswith("|-setboost|{}:".format(side)):
                # parse out the boost information
                boost_type = split_action[3]
                boost_amount = int(split_action[4])
                player_team[pokemon_key]["boosts"][boost_type] = boost_amount
            elif action.startswith("|-heal|{}:".format(side)):
                pokemon_key = split_action[2][2 + len(side) :]
                health = int(split_action[3].split("/")[0])
                player_team[pokemon_key]["hp"] = health
            elif action.startswith("|-damage|{}:".format(side)):
                pokemon_key = split_action[2][2 + len(side) :]
                if split_action[3] == "0 fnt":
                    player_team[pokemon_key]["hp"] = 0
                else:
                    health = int(split_action[3].split("/")[0])
                    player_team[pokemon_key]["hp"] = health
            elif action.startswith("|-status|{}:".format(side)):
                pokemon_key = split_action[2][2 + len(side) :]
                status = split_action[3]
                player_team[pokemon_key]["status"] = status
            elif action.startswith("|-curestatus|{}:".format(side)):
                pokemon_key = split_action[2][2 + len(side) :]
                player_team[pokemon_key]["status"] = None
            elif action.startswith("|-terastallize|{}:".format(side)):
                pokemon_key = split_action[2][2 + len(side) :]
                player_team[pokemon_key]["tera"] = split_action[3]
            elif action.startswith("|detailschange|{}:".format(side)):
                pokemon_key = split_action[2].split(":")[1][1:]
                new_pokemon_name = split_action[3].split(", ")[0]
                if "Zoroak" in new_pokemon_name or "Ditto" in new_pokemon_name:
                    player_team[new_pokemon_name] = player_team.pop(pokemon_key)
                else:
                    player_team[pokemon_key]["name"] = new_pokemon_name
            elif action.startswith("|replace|{}:".format(side)):
                replacing_with_pkm_key = split_action[2].split(": ")[1]
                replacing_with_pkm_name = split_action[3].split(", ")[0]
                to_be_replaced_pkm_key = ""
                # find the pokemon that is being replaced
                for forward_action in event:
                    if forward_action.startswith("|-damage|{}:".format(side)):
                        to_be_replaced_pkm_key = forward_action.split("|")[2][
                            2 + len(side) :
                        ]
                        break
                # replace the pokemon
                player_team[replacing_with_pkm_key] = player_team[
                    to_be_replaced_pkm_key
                ]
                player_team[replacing_with_pkm_key]["name"] = replacing_with_pkm_name
                # clear out the attributes of the replaced pokemon
                player_team[to_be_replaced_pkm_key]["moves"] = set()
                player_team[to_be_replaced_pkm_key]["boosts"] = {}
            elif action.startswith("|-clearallboost"):
                for key in player_team.keys():
                    player_team[key]["boosts"] = {}
            elif action.startswith("|-clearnegativeboost|{}:".format(side)):
                for key in player_team.keys():
                    for boost_type in list(player_team[key]["boosts"].keys()):
                        if player_team[key]["boosts"][boost_type] < 0:
                            player_team[key]["boosts"][boost_type] = 0
            elif action.startswith("|-clearboost|{}:".format(side)):
                pokemon_key = split_action[2][2 + len(side) :]
                player_team[pokemon_key]["boosts"] = {}
            elif action.startswith("|-sethp|{}:".format(side)):
                pokemon_key = split_action[2][2 + len(side) :]
                player_team[pokemon_key]["hp"] = int(split_action[3].split("/")[0])

    return player_team


def find_moveset(team_data, random_sets):
    """
    Finds and updates the moveset for each Pokemon in the team data based on the available random sets.

    Args:
        team_data (dict): A dictionary containing the team data for each Pokemon.
        random_sets (dict): A dictionary containing the available random sets for each Pokemon.

    Returns:
        dict: The updated team data with the movesets modified based on the available random sets.
    """
    for pokemon_name in team_data.keys():
        if len(team_data[pokemon_name]["moves"]) == 4:
            continue
        if pokemon_name in random_sets.keys():
            known_moves = team_data[pokemon_name]["moves"]
            possible_sets = random_sets[pokemon_name]["roles"]
            for role in possible_sets:
                if isinstance(known_moves, dict):
                    known_moves = set(known_moves.keys())
                if known_moves.issubset(possible_sets[role]["moves"]):
                    if "evs" in possible_sets[role]:
                        team_data[pokemon_name]["evs"] = possible_sets[role]["evs"]
                    if "ivs" in possible_sets[role]:
                        team_data[pokemon_name]["ivs"] = possible_sets[role]["ivs"]
                    potential_moveset = possible_sets[role]["moves"]
                    seen_unseen_moves = dict()
                    for move in potential_moveset:
                        if move in known_moves:
                            seen_unseen_moves[move] = "seen"
                        else:
                            seen_unseen_moves[move] = "unseen"
                    team_data[pokemon_name]["moves"] = seen_unseen_moves
                    break
    return team_data


def calculate_damage(atkr: dict, defdr: dict, move_used):
    """
    Calculate the damage inflicted by an attacker on a defender using a specific move.

    Args:
        atkr (dict): The dictionary representing the attacker's attributes.
        defdr (dict): The dictionary representing the defender's attributes.
        move_used: The move used by the attacker.

    Returns:
        float: The calculated damage.
    """
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
    dmg_range = result.damage.valueOf()
    min_dmg = min(dmg_range)
    max_dmg = max(dmg_range)
    # calculate the percentage of damage
    hp = defdr.get("hp")
    if hp == 0:
        return "100%", "100%"
    if hp == None:
        hp = defdr.get("maximum hp")
    min_dmg_percent = int(min_dmg / hp * 100)
    max_dmg_percent = int(max_dmg / hp * 100)
    return str(min_dmg_percent) + "%", str(max_dmg_percent) + "%"


def get_move_effect_on_team(
    atk_pkm_name: str, atk_team: dict, def_team: dict, def_name: str
):
    move_effect = {}
    # find the moves of the attacker
    moves = []
    for key in atk_team.keys():
        if atk_pkm_name in key or key in atk_pkm_name:
            moves = atk_team[key]["moves"]
            break
    if len(moves) == 0:
        return move_effect
    for move in moves:
        move_effect[move] = {}
        if def_name != "":
            move_effect[move][def_name] = calculate_damage(
                atk_team[atk_pkm_name], def_team[def_name], move
            )
            continue
        for def_pkm_name in def_team.keys():
            move_effect[move][def_pkm_name] = calculate_damage(
                atk_team[atk_pkm_name], def_team[def_pkm_name], move
            )
    return move_effect


def find_current_pokemon(side: str, turn_data):
    # look back through the turn data to find the current pokemon
    for event in reversed(turn_data):
        for action in reversed(event):
            if action.startswith("|switch|{}:".format(side)) or action.startswith(
                "|drag|{}:".format(side)
            ):
                return action.split("|")[2].split(": ")[1]


def parse_player_next_turn(turn: List[str], side):
    """
    Parses the player's next turn to determine the action taken.

    Args:
        turn (List[str]): The list of actions performed in the turn.
        side: The side of the player.

    Returns:
        dict: A dictionary containing the chosen action. The dictionary can have the following keys:
            - "move": The move used by the player.
            - "switch": The Pokemon switched to by the player.
            - "faint": The Pokemon that fainted.
            - "status": The status condition of the player's Pokemon.
    """
    chosen_action = {}
    move_chosen = False
    pokemon_chosen = False
    pokemon_fainted = False
    for action in turn:
        if action.startswith("|move|{}:".format(side)) and not move_chosen:
            move_chosen = action.split("|")[3]
            chosen_action["move"] = move_chosen
            move_chosen = True
        elif action.startswith("|switch|{}:".format(side)) and not pokemon_chosen:
            pokemon_switched = action.split("|")[3].split(", ")[0]
            chosen_action["switch"] = pokemon_switched
            pokemon_chosen = True
        elif action.startswith("|faint|{}:".format(side)) and not pokemon_fainted:
            pokemon_fainted = action.split("|")[2]
            chosen_action["faint"] = pokemon_fainted
            pokemon_fainted = True
        elif action.startswith("|cant|{}:".format(side)):
            chosen_action["status"] = action.split("|")[3]
    return chosen_action
