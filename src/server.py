# --- top of server.py ---
import os, json
from dotenv import load_dotenv   # ← add this
load_dotenv()                    # ← and this
from amadeus import Client, ResponseError
from dataclasses import dataclass
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
# -------------------------

from typing import Sequence, List

from mcp.server.fastmcp import FastMCP, Context

# --------------------------------------------------------------------------- #
#                                Lifespan stuff                               #
# --------------------------------------------------------------------------- #
@dataclass
class AppContext:
    amadeus_client: Client


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage Amadeus client lifecycle."""
    api_key = os.environ.get("AMADEUS_API_KEY")
    api_secret = os.environ.get("AMADEUS_API_SECRET")

    if not api_key or not api_secret:
        raise ValueError(
            "AMADEUS_API_KEY and AMADEUS_API_SECRET must be set as environment variables"
        )

    amadeus_client = Client(client_id=api_key, client_secret=api_secret)

    try:
        yield AppContext(amadeus_client=amadeus_client)
    finally:
        # Nothing specific to clean‑up, but we keep the finally block for symmetry
        pass


mcp = FastMCP("Amadeus API", dependencies=["amadeus"], lifespan=app_lifespan)

# --------------------------------------------------------------------------- #
#                              Helper utilities                               #
# --------------------------------------------------------------------------- #
def _json_error(err_msg: str) -> str:
    """Return a uniform JSON error payload."""
    return json.dumps({"error": err_msg})


def _stringify_amadeus_exception(error: ResponseError) -> str:
    body = getattr(error, "response", None)
    # SDK populates .response.body when the API returned JSON
    if body and hasattr(body, "body"):
        try:
            return json.dumps(body.body)
        except Exception:  # pragma: no cover
            return str(error)
    return str(error)


# --------------------------------------------------------------------------- #
#                              ✈ Flight search (existing)                     #
# --------------------------------------------------------------------------- #
@mcp.tool()
def search_flight_offers(
    originLocationCode: str,
    destinationLocationCode: str,
    departureDate: str,
    adults: int,
    ctx: Context,
    returnDate: str = None,
    children: int = None,
    infants: int = None,
    travelClass: str = None,
    includedAirlineCodes: str = None,
    excludedAirlineCodes: str = None,
    nonStop: bool = None,
    currencyCode: str = None,
    maxPrice: int = None,
    max: int = 5,
) -> str:
    """Search for flight offers using the Amadeus API."""
    # (body unchanged – omitted for brevity)
    # ----------------------------------------------------------------------- #


# =========================================================================== #
#                           🏨 NEW HOTEL ENDPOINTS 🏨                         #
# =========================================================================== #

@mcp.tool()
def search_hotels_by_city(
    cityCode: str,
    ctx: Context,
    radius: int = 5,
    radiusUnit: str = "KM",
    chainCodes: str | None = None,
    amenities: str | None = None,
    ratings: str | None = None,
    hotelSource: str = "ALL",
) -> str:
    """
    Find hotels in/around a given IATA city code.

    Args:
        cityCode: 3‑letter IATA city or airport code (e.g. PAR, NYC).
        radius: Search radius around the city centre (1‑300).
        radiusUnit: KM or MILE.
        chainCodes: Comma‑separated list of 2‑letter hotel‑chain codes.
        amenities: Comma‑separated list of amenity keywords (max 3).
        ratings: Comma‑separated list of stars (e.g. "3,4,5").
        hotelSource: BEDBANK | DIRECTCHAIN | ALL
    """
    if len(cityCode) != 3 or not cityCode.isalpha():
        return _json_error("cityCode must be a 3‑letter IATA code")

    amadeus = ctx.request_context.lifespan_context.amadeus_client
    params = {
        "cityCode": cityCode.upper(),
        "radius": radius,
        "radiusUnit": radiusUnit,
        "hotelSource": hotelSource,
    }
    if chainCodes:
        params["chainCodes"] = chainCodes
    if amenities:
        params["amenities"] = amenities
    if ratings:
        params["ratings"] = ratings

    ctx.info(f"Hotel search by city – params: {json.dumps(params)}")
    try:
        resp = amadeus.reference_data.locations.hotels.by_city.get(**params)
        return json.dumps(resp.body)
    except ResponseError as err:
        return _json_error(_stringify_amadeus_exception(err))
    except Exception as exc:
        return _json_error(f"Unexpected error: {exc}")


@mcp.tool()
def search_hotels_by_geocode(
    latitude: float,
    longitude: float,
    ctx: Context,
    radius: int = 5,
    radiusUnit: str = "KM",
    chainCodes: str | None = None,
    amenities: str | None = None,
    ratings: str | None = None,
    hotelSource: str = "ALL",
) -> str:
    """
    Find hotels around a lat/lon coordinate.

    Args mirror the Swagger spec for v1 /reference‑data/locations/hotels/by‑geocode.
    """
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return _json_error("latitude/longitude out of range")

    amadeus = ctx.request_context.lifespan_context.amadeus_client
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "radius": radius,
        "radiusUnit": radiusUnit,
        "hotelSource": hotelSource,
    }
    if chainCodes:
        params["chainCodes"] = chainCodes
    if amenities:
        params["amenities"] = amenities
    if ratings:
        params["ratings"] = ratings

    ctx.info(f"Hotel search by geocode – params: {json.dumps(params)}")
    try:
        resp = amadeus.reference_data.locations.hotels.by_geocode.get(**params)
        return json.dumps(resp.body)
    except ResponseError as err:
        return _json_error(_stringify_amadeus_exception(err))
    except Exception as exc:
        return _json_error(f"Unexpected error: {exc}")


@mcp.tool()
def autocomplete_hotel_name(
    keyword: str,
    ctx: Context,
    subType: str | Sequence[str] = ("HOTEL_LEISURE",),
    countryCode: str | None = None,
    lang: str = "EN",
    max: int = 20,
) -> str:
    """
    Autocomplete hotels by free‑text keyword.

    * `keyword` must be 4‑40 printable chars (Amadeus validation).
    * `subType` → HOTEL_LEISURE or HOTEL_GDS (can repeat param).
    """
    if len(keyword) < 4:
        return _json_error("keyword must be ≥ 4 characters")

    if isinstance(subType, str):
        subType = [subType]

    amadeus = ctx.request_context.lifespan_context.amadeus_client
    params = {"keyword": keyword, "subType": subType, "lang": lang, "max": max}
    if countryCode:
        params["countryCode"] = countryCode.upper()

    ctx.info(f"Hotel name autocomplete – params: {json.dumps(params)}")
    try:
        resp = amadeus.reference_data.locations.hotel.get(**params)
        return json.dumps(resp.body)
    except ResponseError as err:
        return _json_error(_stringify_amadeus_exception(err))
    except Exception as exc:
        return _json_error(f"Unexpected error: {exc}")


@mcp.tool()
def search_hotel_offers(
    hotelIds: List[str],
    ctx: Context,
    checkInDate: str | None = None,
    checkOutDate: str | None = None,
    adults: int = 1,
    roomQuantity: int = 1,
    currency: str | None = None,
    priceRange: str | None = None,
    paymentPolicy: str = "NONE",
    boardType: str | None = None,
    includeClosed: bool = False,
    bestRateOnly: bool = True,
    countryOfResidence: str | None = None,
) -> str:
    """
    Retrieve rate offers for up to 20 specific hotels (v3 /shopping/hotel‑offers).

    Required:
        * hotelIds – list[str] of 8‑char Amadeus property codes.
    """
    if not hotelIds or len(hotelIds) > 20:
        return _json_error("hotelIds must contain 1‑20 items")

    amadeus = ctx.request_context.lifespan_context.amadeus_client
    params: dict = {
        "hotelIds": ",".join(hotelIds),
        "adults": adults,
        "roomQuantity": roomQuantity,
        "includeClosed": includeClosed,
        "bestRateOnly": bestRateOnly,
        "paymentPolicy": paymentPolicy,
    }
    # Optional filters
    if checkInDate:
        params["checkInDate"] = checkInDate
    if checkOutDate:
        params["checkOutDate"] = checkOutDate
    if currency:
        params["currency"] = currency
    if priceRange:
        params["priceRange"] = priceRange
    if boardType:
        params["boardType"] = boardType
    if countryOfResidence:
        params["countryOfResidence"] = countryOfResidence

    ctx.info(f"Hotel offers search – params: {json.dumps(params)}")
    try:
        resp = amadeus.shopping.hotel_offers_search.get(**params)
        return json.dumps(resp.body)
    except ResponseError as err:
        return _json_error(_stringify_amadeus_exception(err))
    except Exception as exc:
        return _json_error(f"Unexpected error: {exc}")


# --------------------------------------------------------------------------- #
#                               Prompt helper                                 #
# --------------------------------------------------------------------------- #
@mcp.prompt()
def hotel_search_prompt(city: str, check_in: str, check_out: str) -> str:
    """Generate a friendly prompt for hotel‑search usage examples."""
    return (
        f"Find me hotel options in {city} from {check_in} to {check_out}. "
        "Show rates, board type, and cancellation policy, sorted by total price."
    )


@mcp.prompt()
def flight_search_prompt(origin: str, destination: str, date: str) -> str:
    """(unchanged)"""
    return (
        f"Please search for flights from {origin} to {destination} on {date}.\n\n"
        "I'd like to see options sorted by price, with information about the airlines,\n"
        "departure/arrival times, and any layovers."
    )

# --------------------------------------------------------------------------- #
#                                   Main                                      #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    mcp.run()
