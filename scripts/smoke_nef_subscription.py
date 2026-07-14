import asyncio
import json

from app.config import get_settings
from app.nef_client import NefClient


async def main() -> None:
    settings = get_settings()
    subscription_id: str | None = None

    async with NefClient(settings) as client:
        token = await client.get_access_token()

        payload = client.build_as_session_payload(
            ue_ipv4="10.61.0.1",
            guaranteed_bandwidth="10 Mbps",
            maximum_bandwidth="20 Mbps",
        )

        print("TOKEN_RECEBIDO=SIM")
        print("PAYLOAD:")
        print(json.dumps(payload, indent=2))

        try:
            subscription = await client.create_as_session(
                token=token,
                payload=payload,
            )

            subscription_id = subscription.subscription_id

            print("CREATE_HTTP=201")
            print("SUBSCRIPTION_ID=", subscription.subscription_id)
            print("LOCATION=", subscription.location)

            await asyncio.sleep(3)

        finally:
            if subscription_id is not None:
                await client.delete_as_session(
                    token=token,
                    subscription_id=subscription_id,
                )

                print("DELETE_HTTP=204")
                print("CICLO_QOD=SUCESSO")


if __name__ == "__main__":
    asyncio.run(main())
