import asyncio
import json
import names

from datetime import datetime, timezone
from typing import Literal, Tuple, Any
from curl_cffi.requests import AsyncSession

from models import Account
from .exceptions.base import APIError
from loader import ocr_solver


class DawnExtensionAPI:
    API_URL = "https://www.aeropres.in/chromeapi/dawn"

    def __init__(self, account: Account):
        self.account_data = account
        self.wallet_data: dict[str, Any] = {}
        self.session = self.setup_session()

    def setup_session(self) -> AsyncSession:
        session = AsyncSession(impersonate="chrome124", verify=False)
        session.timeout = 30
        session.headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "origin": "chrome-extension://fpdkjdnhkakefebpekbdhillbhonfjjp",
            "priority": "u=1, i",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        }

        if self.account_data.proxy:
            session.proxies = {
                "http": self.account_data.proxy.as_url,
                "https": self.account_data.proxy.as_url,
            }

        return session

    async def clear_request(self, url: str):
        session = AsyncSession(impersonate="chrome124", verify=False, timeout=30)
        session.proxies = self.session.proxies

        response = await session.get(url)
        return response

    async def send_request(
        self,
        request_type: Literal["POST", "GET", "OPTIONS"] = "POST",
        method: str = None,
        json_data: dict = None,
        params: dict = None,
        url: str = None,
        headers: dict = None,
        cookies: dict = None,
        verify: bool = True,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        def verify_response(response_data: dict | list) -> dict | list:
            if "status" in str(response_data):
                if isinstance(response_data, dict):
                    if response_data.get("status") is False:
                        raise APIError(f"API returned an error: {response_data}", response_data)

            elif "success" in str(response_data):
                if isinstance(response_data, dict):
                    if response_data.get("success") is False:
                        raise APIError(f"API returned an error: {response_data}", response_data)

            return response_data

        for attempt in range(max_retries):
            try:
                if request_type == "POST":
                    if not url:
                        response = await self.session.post(
                            f"{self.API_URL}{method}",
                            json=json_data,
                            params=params,
                            headers=headers if headers else self.session.headers,
                            cookies=cookies,
                        )
                    else:
                        response = await self.session.post(
                            url,
                            json=json_data,
                            params=params,
                            headers=headers if headers else self.session.headers,
                            cookies=cookies,
                        )
                elif request_type == "OPTIONS":
                    response = await self.session.options(
                        url,
                        headers=headers if headers else self.session.headers,
                        cookies=cookies,
                    )
                else:
                    if not url:
                        response = await self.session.get(
                            f"{self.API_URL}{method}",
                            params=params,
                            headers=headers if headers else self.session.headers,
                            cookies=cookies,
                        )
                    else:
                        response = await self.session.get(
                            url,
                            params=params,
                            headers=headers if headers else self.session.headers,
                            cookies=cookies,
                        )

                if verify:
                    try:
                        return verify_response(response.json())
                    except json.JSONDecodeError:
                        response.raise_for_status()
                        return response.text

                return response.text

            except APIError:
                raise

            except Exception as error:
                if attempt == max_retries - 1:
                    raise APIError(
                        f"Failed to send request after {max_retries} attempts: {error}"
                    )
                await asyncio.sleep(retry_delay)

        raise APIError(f"Failed to send request after {max_retries} attempts")

    @staticmethod
    async def solve_puzzle(image: str) -> Tuple[str | int, bool]:
        response = ocr_solver.start(image)
        return response

    async def get_puzzle_id(self) -> str:
        response = await self.send_request(
            method="/v1/puzzle/get-puzzle",
            request_type="GET",
        )

        return response["puzzle_id"]

    async def get_puzzle_image(self, puzzle_id: str) -> str:
        response = await self.send_request(
            method="/v1/puzzle/get-puzzle-image",
            request_type="GET",
            params={"puzzle_id": puzzle_id},
        )

        return response.get("imgBase64")

    async def register(self, puzzle_id: str, answer: str) -> dict:
        json_data = {
            "firstname": names.get_first_name(),
            "lastname": names.get_last_name(),
            "email": self.account_data.email,
            "mobile": "",
            "password": self.account_data.password,
            "country": "+84",
            "referralCode": "y2bj41gn",
            "puzzle_id": puzzle_id,
            "ans": answer,
        }

        return await self.send_request(
            method="/v1/puzzle/validate-register",
            json_data=json_data,
        )

    async def keepalive(self) -> dict | str:
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9,ru;q=0.8',
            'authorization': f'Berear {self.session.headers["Berear"]}',
            'content-type': 'application/json',
            'origin': 'chrome-extension://fpdkjdnhkakefebpekbdhillbhonfjjp',
            'user-agent': self.session.headers["user-agent"],
        }

        json_data = {
            "username": self.account_data.email,
            "extensionid": "fpdkjdnhkakefebpekbdhillbhonfjjp",
            "numberoftabs": 0,
            "_v": "1.0.7",
        }

        return await self.send_request(
            method="/v1/userreward/keepalive",
            json_data=json_data,
            verify=False,
            headers=headers,
        )

    async def user_info(self) -> dict:
        headers = self.session.headers.copy()
        headers["authorization"] = f'Berear {self.session.headers["Berear"]}'
        headers["content-type"] = "application/json"
        del headers["Berear"]

        response = await self.send_request(
            url="https://www.aeropres.in/api/atom/v1/userreferral/getpoint",
            request_type="GET",
            headers=headers,
        )

        return response["data"]

    async def complete_tasks(self, tasks: list[str] = None, delay: int = 1) -> None:
        if not tasks:
            tasks = ["telegramid", "discordid", "twitter_x_id"]

        headers = self.session.headers.copy()
        headers["authorization"] = f'Brearer {self.session.headers["Berear"]}'
        headers["content-type"] = "application/json"
        del headers["Berear"]

        for task in tasks:
            json_data = {
                task: task,
            }

            await self.send_request(
                method="/v1/profile/update",
                json_data=json_data,
                headers=headers,
            )

            await asyncio.sleep(delay)

    async def verify_session(self) -> bool:
        try:
            await self.user_info()
            return True

        except APIError:
            return False

    async def login(self, puzzle_id: str, answer: str):
        current_time = datetime.now(timezone.utc)
        formatted_datetime_str = (
            current_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        )

        json_data = {
            "username": self.account_data.email,
            "password": self.account_data.password,
            "logindata": {
                "_v": "1.0.7",
                "datetime": formatted_datetime_str,
            },
            "puzzle_id": puzzle_id,
            "ans": answer,
        }

        response = await self.send_request(
            method="/v1/user/login/v2",
            json_data=json_data,
        )

        berear = response.get("data", {}).get("token")
        if berear:
            self.wallet_data = response.get("data", {}).get("wallet")
            self.session.headers.update({"Berear": berear})
        else:
            raise APIError(f"Failed to login: {response}")
