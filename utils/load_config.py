import os
import yaml

from itertools import cycle
from loguru import logger
from models import Config, Account
from better_proxy import Proxy

CONFIG_PATH = os.path.join(os.getcwd(), "config")
CONFIG_DATA_PATH = os.path.join(CONFIG_PATH, "data")
CONFIG_PARAMS = os.path.join(CONFIG_PATH, "settings.yaml")

REQUIRED_DATA_FILES = ("accounts.txt", "proxies.txt")
REQUIRED_PARAMS_FIELDS = (
    "threads",
    "anti_captcha_api_key",
    "keepalive_interval",
    "imap_settings",
)


def read_file(
    file_path: str, check_empty: bool = True, is_yaml: bool = False
) -> list[str] | dict:
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        exit(1)

    if check_empty and os.stat(file_path).st_size == 0:
        logger.error(f"File is empty: {file_path}")
        exit(1)

    if is_yaml:
        with open(file_path, "r") as file:
            data = yaml.safe_load(file)
        return data

    with open(file_path, "r") as file:
        data = file.readlines()

    return [line.strip() for line in data]


def get_params() -> dict:
    data = read_file(CONFIG_PARAMS, is_yaml=True)

    for field in REQUIRED_PARAMS_FIELDS:
        if field not in data:
            logger.error(f"Field '{field}' is missing in config file")
            exit(1)

    return data


def get_proxies() -> list[Proxy]:
    try:
        proxies = read_file(
            os.path.join(CONFIG_DATA_PATH, "proxies.txt"), check_empty=False
        )
        if proxies:
            return [Proxy.from_str(line) for line in proxies]
        else:
            return []
    except Exception as exc:
        logger.error(f"Failed to parse proxy: {exc}")
        exit(1)


def get_accounts_to_register():
    proxies = get_proxies()
    proxy_cycle = cycle(proxies) if proxies else None
    accounts = read_file(
        os.path.join(CONFIG_DATA_PATH, "register.txt"), check_empty=True
    )

    for account in accounts:
        email, password = account.split(":")
        yield Account(
            email=email,
            password=password,
            proxy=next(proxy_cycle) if proxy_cycle else None,
        )


def get_accounts_to_farm():
    proxies = get_proxies()
    proxy_cycle = cycle(proxies) if proxies else None
    accounts = read_file(os.path.join(CONFIG_DATA_PATH, "farm.txt"), check_empty=True)

    for account in accounts:
        email, password = account.split(":")
        yield Account(
            email=email,
            password=password,
            proxy=next(proxy_cycle) if proxy_cycle else None,
        )


def validate_domains(accounts: list[Account], domains: dict):
    for account in accounts:
        domain = account.email.split("@")[1]
        if domain not in domains:
            logger.error(
                f"Domain '{domain}' is not supported, please add it to the config file"
            )
            exit(1)

        imap_server = domains[domain]
        account.imap_server = imap_server

    return accounts


def load_config() -> Config:
    reg_accounts = list(get_accounts_to_register())
    farm_accounts = list(get_accounts_to_farm())

    if not reg_accounts and not farm_accounts:
        logger.error("No accounts found in data files")
        exit(1)

    config = Config(
        **get_params(),
        accounts_to_farm=farm_accounts,
        accounts_to_register=reg_accounts,
    )

    if reg_accounts:
        accounts = validate_domains(reg_accounts, config.imap_settings)
        config.accounts_to_register = accounts

    return config