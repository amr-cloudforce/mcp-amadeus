from typing import Any
import asyncio
import os
import json
from amadeus import Client, ResponseError
import httpx
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

AMADEUS_API_KEY = None
AMADEUS_API_SECRET = None

server = Server("amadeus-api")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="search_flight_offers",
            description="Search for flight offers using the Amadeus API",
            inputSchema={
                "type": "object",
                "properties": {
                    "originLocationCode": {
                        "type": "string",
                        "description": "IATA code of the departure city/airport (e.g., SYD for Sydney)."
                    },
                    "destinationLocationCode": {
                        "type": "string",
                        "description": "IATA code of the destination city/airport (e.g., BKK for Bangkok)."
                    },
                    "departureDate": {
                        "type": "string",
                        "description": "Departure date in ISO 8601 format (YYYY-MM-DD, e.g., 2023-05-02)."
                    },
                    "adults": {
                        "type": "integer",
                        "description": "Number of adult travelers (age 12+), must be 1-9.",
                        "minimum": 1,
                        "maximum": 9
                    },
                    "returnDate": {
                        "type": "string",
                        "description": "Return date in ISO 8601 format (YYYY-MM-DD), if round-trip is desired."
                    },
                    "children": {
                        "type": "integer",
                        "description": "Number of child travelers (age 2-11).",
                        "minimum": 0,
                        "default": 0
                    },
                    "infants": {
                        "type": "integer",
                        "description": "Number of infant travelers (age <= 2).",
                        "minimum": 0,
                        "default": 0
                    },
                    "travelClass": {
                        "type": "string",
                        "description": "Travel class",
                        "enum": ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"],
                    },
                    "includedAirlineCodes": {
                        "type": "string",
                        "description": "Comma-separated IATA airline codes to include (e.g., '6X,7X')."
                    },
                    "excludedAirlineCodes": {
                        "type": "string",
                        "description": "Comma-separated IATA airline codes to exclude (e.g., '6X,7X')."
                    },
                    "nonStop": {
                        "type": "string",
                        "description": "If true, only non-stop flights are returned.",
                        "enum": ["true", "false"],
                        "default": "false"
                    },
                    "currencyCode": {
                        "type": "string",
                        "description": "ISO 4217 currency code (e.g., EUR for Euro)."
                    },
                    "maxPrice": {
                        "type": "integer",
                        "description": "Maximum price per traveler, positive integer with no decimals.",
                        "minimum": 1
                    },
                    "max": {
                        "type": "integer",
                        "description": "Maximum number of flight offers to return.",
                        "minimum": 1,
                        "maximum": 250,
                        "default": 250
                    }
                },
                "required": ["originLocationCode", "destinationLocationCode", "departureDate", "adults"],
            }
        )
    ]

async def make_amadeus_request(params: dict) -> dict[str, Any] | None:
    """Make a request to the Amadeus API with proper error handling."""
    try:

        amadeus = Client(
            client_id=AMADEUS_API_KEY,
            client_secret=AMADEUS_API_SECRET,
            # hostname='production'
        )


        response = amadeus.shopping.flight_offers_search.get(**params)
        return response.body

    except ResponseError as error:
        return {"error": f"Amadeus API error: {str(error)}"}

    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Currently supported tools:
    - search_flight_offers: Search for flight offers using the Amadeus API
    """
    if name == "search_flight_offers":

        if arguments is None:
            return [types.TextContent(type="text", text="No arguments provided")]

        required_params = ["originLocationCode", "destinationLocationCode", "departureDate", "adults"]
        for param in required_params:
            if param not in arguments:
                return [types.TextContent(type="text", text=f"Missing required parameter: {param}")]

        params = {
            "originLocationCode": arguments.get("originLocationCode"),
            "destinationLocationCode": arguments.get("destinationLocationCode"),
            "departureDate": arguments.get("departureDate"),
            "adults": arguments.get("adults"),
            "children": arguments.get("children", 0),
            "infants": arguments.get("infants", 0),
            "nonStop": arguments.get("nonStop", "false"),
            "max": arguments.get("max", 250),
        }

        if "returnDate" in arguments:
            params["returnDate"] = arguments["returnDate"]
        if "travelClass" in arguments:
            params["travelClass"] = arguments["travelClass"].upper()
        if "includedAirlineCodes" in arguments:
            params["includedAirlineCodes"] = arguments["includedAirlineCodes"]
        if "excludedAirlineCodes" in arguments:
            params["excludedAirlineCodes"] = arguments["excludedAirlineCodes"]
        if "currencyCode" in arguments:
            params["currencyCode"] = arguments["currencyCode"]
        if "maxPrice" in arguments:
            params["maxPrice"] = arguments["maxPrice"]

        flight_data = await make_amadeus_request(params)

        if not flight_data:
            return [types.TextContent(type="text", text="Failed to retrieve flight data")]

        return [
            types.TextContent(
                type="text",
                text=json.dumps(flight_data)
            )
        ]
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main(api_key: str, api_secret: str):
    global AMADEUS_API_KEY, AMADEUS_API_SECRET
    AMADEUS_API_KEY = api_key
    AMADEUS_API_SECRET = api_secret

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="amadeus-api",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    api_key = os.environ.get("AMADEUS_API_KEY")
    api_secret = os.environ.get("AMADEUS_API_SECRET")

    if not api_key or not api_secret:
        print("Error: AMADEUS_API_KEY and AMADEUS_API_SECRET must be set as environment variables")
        exit(1)

    asyncio.run(main(api_key, api_secret))
