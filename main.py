import asyncio
import logging
import os
import json
import sys

from dotenv import load_dotenv

# Load .env file
load_dotenv()

from utils import (
    request,
    download_json,
    push_to_github,
    load_commit_local,
    save_commit_local,
    save_data
)

# API GIT
GIT2="https://gitlab.com/api/v4/{PATH}"
RAW_GIT2 = "https://gitlab.com/{PATH}"

# Logging
logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

# GIT
USERNAME = os.getenv('GITHUB_USERNAME')
REPOSITORY = os.getenv('GITHUB_REPOSITORY')
PROJECT_ID = os.getenv('GITHUB_PROJECT_ID')
PROJECT_BRANCH = os.getenv('GITHUB_PROJECT_BRANCH')

# Check is DEV_MODE
DEVMODE = sys.argv[1] == "dev" if len(sys.argv) > 1 else False
BYPASS = sys.argv[2] == "bypass" if len(sys.argv) > 2 else False
SKIP_DOWNLOAD = sys.argv[3] == "skip_download" if len(sys.argv) > 3 else False

# ENV
ENVKEY = [
    "AVATAR",
    "SKILLDEPOT",
    "SKILLS",
    "TALENTS",
    "ARTIFACTS",
    "WEAPONS",
    "FIGHT_PROPS",
    "NAMECARDS",
    "ARTIFACTS_SETS",
    "COSTUME",
    "PROPS_MAP",
    "ARTIFACT_PROPS_MAIN",
    "ARTIFACT_PROPS_SUB"
]
SKIP_HASH = ["artifact_props"]

LANGS = {}
DATA = {}
SKILLS_DEPOT = {}

async def create_lang(data: dict, filename: str = "", has_key_name_hash: bool = True):
    DATA = {}
    for key in data:
        hash_map = str(data[key]["nameTextMapHash"])
        hashKey = key if not has_key_name_hash else hash_map
        
        for lang in LANGS:
            if hash_map in LANGS[lang]:
                if hashKey not in DATA:
                    DATA[hashKey] = {}
                DATA[hashKey][lang] = LANGS[lang][hash_map]
            else:
                if hash_map not in DATA:
                    DATA[hashKey] = {}
                DATA[hashKey][lang] = ""

    with open(os.path.join("exports", "langs", filename), "w", encoding="utf-8") as f:
        f.write(json.dumps(DATA, ensure_ascii=False, indent=4))

async def main():
    EXPORT_DATA = {}

    LOGGER.debug(f"Fetching commits from Git. [{USERNAME}/{REPOSITORY}]")
    response = await request(GIT2.format(PATH=f"/projects/{PROJECT_ID}/repository/commits"))
    # print(response)

    # Check SHA of last commit
    LOGGER.debug(f"Checking last commit on Git...")
    if len(response) > 0:
        last_commit = response[0]["id"]
        last_message = response[0]["title"]
        LOGGER.debug(f"Last commit on Git: {last_commit}")
    else:
        LOGGER.debug("No commits found on Git...")
        last_commit = ""

    LOGGER.debug(f"Checking last commit on local...")
    last_commit_local = await load_commit_local()
    if last_commit_local == last_commit and not BYPASS  :
        LOGGER.debug(f"Not updated... exiting...")
        return

    LOGGER.debug(f"New commit found on git")

    if not SKIP_DOWNLOAD:
        for key in ENVKEY:
            print(key)
            filename = os.getenv(key)
            if not filename:
                LOGGER.error(f"{key} not found in .env")
                continue

            await download_json(
                url=RAW_GIT2.format(PATH=f"{USERNAME}/{REPOSITORY}/-/raw/{PROJECT_BRANCH}/{os.getenv('FOLDER')}/{filename}"), 
                filename=filename, 
                path=os.path.join("raw", "data")
            )

    await asyncio.sleep(1)

    if not SKIP_DOWNLOAD:
        langPath = await request(GIT2.format(PATH=f"/projects/{PROJECT_ID}/repository/tree?recursive=true&path={os.getenv('LANG_FOLDER')}"))
        for lang in langPath:
            await download_json(
                url=RAW_GIT2.format(PATH=f"{USERNAME}/{REPOSITORY}/-/raw/{PROJECT_BRANCH}/{lang['path']}"),
                filename=lang["name"],
                path=os.path.join("raw", "langs")
            )

    # Load langs 
    for lang in os.listdir(os.path.join("raw", "langs")):
        if lang.endswith(".json"):
            with open(os.path.join("raw", "langs", lang), "r", encoding="utf-8") as f:
                _lang = lang.split(".")[0].replace("TextMap", "")
                LOGGER.debug(f"Loading lang ({_lang})...")
                LANGS[_lang] = json.loads(f.read())

    # Load data 
    for data in os.listdir(os.path.join("raw", "data")):
        if data.endswith(".json"):
            with open(os.path.join("raw", "data", data), "r", encoding="utf-8") as f:
                _key = data.split(".")[0]
                LOGGER.debug(f"Loading data ({_key})...")
                DATA[data.split(".")[0]] = json.loads(f.read())

    # Load skills data
    for skillData in DATA["AvatarSkillExcelConfigData"]:
        LOGGER.debug(f"Getting skill data {skillData['id']}...")
        if skillData["skillIcon"] == "":
            LOGGER.debug(f"Skill {skillData['id']} has no icon... Skipping...")
            continue

        if not "skills" in EXPORT_DATA:
            EXPORT_DATA["skills"] = {}

        EXPORT_DATA["skills"][skillData["id"]] = {
            "nameTextMapHash": skillData["nameTextMapHash"],
            "skillIcon": skillData["skillIcon"],
            "forceCanDoSkill": skillData.get("forceCanDoSkill", None),
            "costElemType": skillData.get("costElemType", ""),
            "proudSkillGroupId": skillData.get("proudSkillGroupId","")
        } 

    # Load constellations
    for talent in DATA["AvatarTalentExcelConfigData"]:
        LOGGER.debug(f"Getting constellations {talent['talentId']}...")
        
        if not "constellations" in EXPORT_DATA:
            EXPORT_DATA["constellations"] = {}

        EXPORT_DATA["constellations"][talent["talentId"]] = {
            "nameTextMapHash": talent["nameTextMapHash"],
            "icon": talent["icon"]
        }

    # Load artifacts
    for artifact in DATA["ReliquaryExcelConfigData"]:
        LOGGER.debug(f"Getting artifact {artifact['id']}...")

        if not "artifacts" in EXPORT_DATA:
            EXPORT_DATA["artifacts"] = {}
            
        EXPORT_DATA["artifacts"][artifact["id"]] = {
            "nameTextMapHash": artifact["nameTextMapHash"],
            "itemType": artifact["itemType"],
            "equipType": artifact["equipType"],
            "icon": artifact["icon"],
            "rankLevel": artifact["rankLevel"],
            "mainPropDepotId": artifact["mainPropDepotId"],
            "appendPropDepotId": artifact["appendPropDepotId"],
        }

    # Load artifacts sets
    for artifactSet in DATA["EquipAffixExcelConfigData"]:
        LOGGER.debug(f"Getting artifact set {artifactSet['affixId']}...")
        if not "artifact_sets" in EXPORT_DATA:
            EXPORT_DATA["artifact_sets"] = {}

        if  artifactSet["openConfig"].startswith("Relic_") or \
            artifactSet["openConfig"].startswith("Relci_"):
            EXPORT_DATA["artifact_sets"][artifactSet["affixId"]] = {
                "affixId": artifactSet["affixId"],
                "nameTextMapHash": artifactSet["nameTextMapHash"],
            }

    # Load artifact props (Main & Sub)
    ARTIFACT_PROPS = []
    ARTIFACT_PROPS.extend(DATA["ReliquaryMainPropExcelConfigData"])
    ARTIFACT_PROPS.extend(DATA["ReliquaryAffixExcelConfigData"])
    PERCENT = ['HURT','CRITICAL','EFFICIENCY','PERCENT','ADD']

    for artifactProps in ARTIFACT_PROPS:
        if not "artifact_props" in EXPORT_DATA:
            EXPORT_DATA["artifact_props"] = {}

        # Check percent and get raw value
        ISPERCENT = artifactProps['propType'].split("_")[-1] in PERCENT
        RAW = artifactProps.get("propValue", 0)

        EXPORT_DATA["artifact_props"][artifactProps["id"]] = {
            'propType': artifactProps['propType'],
            'propDigit': 'PERCENT' if ISPERCENT else 'DIGIT',
            'propValue': round(RAW * 100, 1) if ISPERCENT else round(RAW)
        }
        
    # Load weapons
    for weapon in DATA["WeaponExcelConfigData"]:
        LOGGER.debug(f"Getting weapon {weapon['id']}...")

        if not "weapons" in EXPORT_DATA:
            EXPORT_DATA["weapons"] = {}

        EXPORT_DATA["weapons"][weapon["id"]] = {
            "nameTextMapHash": weapon["nameTextMapHash"],
            "icon": weapon["icon"],
            "awakenIcon": weapon["awakenIcon"],
            "rankLevel": weapon["rankLevel"]
        }
    
    # Load namecard
    for namecard in filter(lambda a: "materialType" in a and a["materialType"] == "MATERIAL_NAMECARD", DATA["MaterialExcelConfigData"]):
        LOGGER.debug(f"Getting namecard {namecard['id']}...")

        if not "namecards" in EXPORT_DATA:
            EXPORT_DATA["namecards"] = {}

        EXPORT_DATA["namecards"][namecard["id"]] = {
            "nameTextMapHash": namecard["nameTextMapHash"],
            "icon": namecard["icon"],
            "picPath": namecard["picPath"],
            "rankLevel": namecard["rankLevel"],
            "materialType": namecard["materialType"],
        }

    # Load fight props
    for fight_prop in filter(lambda a: a['textMapId'].startswith("FIGHT_PROP"), DATA["ManualTextMapConfigData"]):
        LOGGER.debug(f"Getting FIGHT_PROP {fight_prop['textMapId']}...")

        if not "fight_props" in EXPORT_DATA:
            EXPORT_DATA["fight_props"] = {}

        EXPORT_DATA["fight_props"][fight_prop["textMapId"]] = {
            "nameTextMapHash": fight_prop["textMapContentTextMapHash"],
        }

    # Prepare data (Create language)
    for skillDepot in DATA["AvatarSkillDepotExcelConfigData"]:
        LOGGER.debug(f"Getting skill depot: {skillDepot['id']}...")
        SKILLS_DEPOT[skillDepot["id"]] = skillDepot
        
    # Characters costumes
    _key = {
        "costumeId": "",
        "iconName": ""
    }
    for costume in DATA["AvatarCostumeExcelConfigData"]:
        if _key["costumeId"] == "" or _key["iconName"] == "":
            # Find key costumeId
            LOGGER.debug("Find key 'costumeId' and 'iconName'")
            for key in costume:
                _valstr = str(costume[key])
                if _valstr.startswith("2") and len(_valstr) == 6:
                    LOGGER.debug(f"Get key 'costumeId' is: {key}")
                    _key["costumeId"] = key
                    continue

                if _valstr.startswith("UI_AvatarIcon_") and \
                    not _valstr.startswith("UI_AvatarIcon_Side_"):
                    LOGGER.debug(f"Get key 'iconName' is: {key}")
                    _key["iconName"] = key
                    continue

        LOGGER.debug(f"Getting character costume: {costume[_key['costumeId']]}...")
        if not "costumes" in EXPORT_DATA:
            EXPORT_DATA["costumes"] = {}

        if not _key['iconName'] in costume or costume[_key['iconName']] == "":
            LOGGER.debug(f"Character costume {costume[_key['costumeId']]} has no data... Skpping...")
            continue

        EXPORT_DATA["costumes"][costume[_key['costumeId']]] = {
            "iconName": costume[_key['iconName']],
            "sideIconName": costume["sideIconName"],
            "nameTextMapHash": costume["nameTextMapHash"],
        }
    
    # Link data (Avatar)
    for avatar in DATA["AvatarExcelConfigData"]:
        AVATAR = {}
        LOGGER.debug(f"Processing {avatar['id']}...")
        if avatar["skillDepotId"] == 101 or \
            avatar["iconName"].endswith("_Kate") or \
            str(avatar['id'])[:2] == "11": # 11 is test character mode 
            LOGGER.debug(f"Skipping {avatar['id']}...")
            continue

        if not "characters" in EXPORT_DATA:
            EXPORT_DATA["characters"] = {}

        AVATAR.update({
            "nameTextMapHash": avatar["nameTextMapHash"],
            "iconName": avatar["iconName"],
            "sideIconName": avatar["sideIconName"],
            "qualityType": avatar["qualityType"],
            "costElemType": "",
            "skills": [],
            "talents": []
        })

        if avatar["iconName"].endswith("_PlayerBoy") or \
            avatar["iconName"].endswith("_PlayerGirl"):
            LOGGER.debug("Getting skill (candSkillDepotIds): {}...".format(avatar["candSkillDepotIds"]))

            for cand_depot in avatar["candSkillDepotIds"]:
                AVATAR.update({
                    "skills": [],
                    "talents": []
                })

                depot = SKILLS_DEPOT.get(cand_depot)
                if depot and depot["id"] != 101:
                    for skill in depot["skills"]:
                        if skill <= 0:
                            continue

                        AVATAR["skills"].append(skill)

                    energry = EXPORT_DATA["skills"].get(depot.get("energySkill"))

                    if energry:
                        LOGGER.debug(f"Getting skills element {depot.get('energySkill')}")
                        AVATAR.update({
                            "costElemType": energry["costElemType"]
                        })
                        AVATAR["skills"].append(int(depot.get('energySkill')))

                    AVATAR.update({
                        "talents": [x for x in depot["talents"] if x > 0],
                    })

                    EXPORT_DATA["characters"][str(avatar["id"]) + "-" + str(depot["id"])] = AVATAR.copy()

            AVATAR.update({
                "skills": [],
                "talents": []
            })
                
            EXPORT_DATA["characters"][str(avatar["id"])] = AVATAR.copy()

        else:
            LOGGER.debug(f"Getting skills {avatar['skillDepotId']}")
            depot = SKILLS_DEPOT.get(avatar["skillDepotId"])
            if depot and depot["id"] != 101:
                for skill in depot["skills"]:
                    if skill <= 0:
                        continue

                    # Check if skill is alternative
                    skill_info = EXPORT_DATA["skills"].get(int(skill))
                    if not skill_info["forceCanDoSkill"] is None:
                         continue
                
                    AVATAR["skills"].append(skill)

                energry = EXPORT_DATA["skills"].get(depot.get("energySkill"))

                if energry:
                    LOGGER.debug(f"Getting skills element {depot.get('energySkill')}")
                    AVATAR.update({
                        "costElemType": energry["costElemType"]
                    })
                    AVATAR["skills"].append(int(depot.get('energySkill')))


                AVATAR.update({
                    "talents": [x for x in depot["talents"] if x > 0],
                })
        
            EXPORT_DATA["characters"][avatar["id"]] = AVATAR

    LOGGER.debug("Exporting data...")
    for key in EXPORT_DATA:
        _delKey = []
        if key == "skills":
            _delKey.append("costElemType")
            _delKey.append("forceCanDoSkill")

        LOGGER.debug(f"Exporting {key}...")
        await save_data(EXPORT_DATA[key], f"{key}.json", _delKey)
        if not key in SKIP_HASH:
            await create_lang(EXPORT_DATA[key], f"{key}.json", False if key in ["fight_props"] else True)  

    # Push to github
    if not DEVMODE:
        await push_to_github(f"""{last_message}
    - SHA: *********{last_commit[10:15]}************
    - URL: [private]
        """)

    # Save lastest commit
    LOGGER.debug(f"Saving lastest commit...")
    await save_commit_local(last_commit)

    LOGGER.debug(f"Done!")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
