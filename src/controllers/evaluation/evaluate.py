import hashlib

actions_file_name = "data/actions.json"


def get_json_hash() -> str:
    with open(actions_file_name) as actions:
        return str(
            int(hashlib.sha1((actions.read()).encode("utf-8")).hexdigest(), 16)
            % (10**8)
        )
