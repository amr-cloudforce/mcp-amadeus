# ────────────────────────────────────────────────────────────────────────────
# server.py  –  FastMCP + raw HTTP flight‑offers  (05‑May‑2025)
# ────────────────────────────────────────────────────────────────────────────
import os, json, time
from typing     import Sequence, List
from dataclasses import dataclass
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from dotenv import load_dotenv
import requests
from amadeus      import Client, ResponseError
from mcp.server.fastmcp import FastMCP, Context

load_dotenv()                                           # read .env creds

AMA_HOST   = "https://test.api.amadeus.com"
TOKEN_URL  = f"{AMA_HOST}/v1/security/oauth2/token"
FLIGHT_URL = f"{AMA_HOST}/v2/shopping/flight-offers"

AMA_KEY    = os.getenv("AMADEUS_API_KEY")
AMA_SECRET = os.getenv("AMADEUS_API_SECRET")
if not AMA_KEY or not AMA_SECRET:
    raise RuntimeError("AMADEUS_API_KEY / _SECRET must be set in env/.env")

# ─────────────────────────── OAuth helper ──────────────────────────────────
class OAuthSession:
    """Minimal bearer‑token manager around `requests.Session`."""
    def __init__(self, key: str, secret: str) -> None:
        self._key     = key
        self._secret  = secret
        self._token   = None
        self._expires = 0.0
        self.session  = requests.Session()

    def _refresh(self) -> None:
        data = {
            "grant_type": "client_credentials",
            "client_id": self._key,
            "client_secret": self._secret,
        }
        r = self.session.post(TOKEN_URL, data=data, timeout=15)
        r.raise_for_status()
        payload = r.json()
        self._token   = payload["access_token"]
        self._expires = time.time() + payload.get("expires_in", 1700) - 30

    def headers(self) -> dict:
        if not self._token or time.time() >= self._expires:
            self._refresh()
        return {"Authorization": f"Bearer {self._token}"}

# ───────────────────────────── Lifespan ────────────────────────────────────
@dataclass
class AppContext:
    amadeus_sdk : Client
    oauth       : OAuthSession

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    sdk   = Client(client_id=AMA_KEY, client_secret=AMA_SECRET)
    oauth = OAuthSession(AMA_KEY, AMA_SECRET)
    try:
        yield AppContext(amadeus_sdk=sdk, oauth=oauth)
    finally:
        pass

mcp = FastMCP("Amadeus API", dependencies=["amadeus","requests"], lifespan=app_lifespan)

def _json_error(msg:str)->str: return json.dumps({"error":msg})
def _stringify(err:ResponseError)->str:
    bod=getattr(err,"response",None)
    if bod and hasattr(bod,"body"):
        try: return json.dumps(bod.body)
        except: pass
    return str(err)

# ═════════════════════ ✈  RAW FLIGHT SEARCH (POST) ════════════════════════
@mcp.tool()
def search_flight_offers(
    originLocationCode      : str,
    destinationLocationCode : str,
    departureDate           : str,
    adults                  : int,
    ctx : Context,
    returnDate              : str|None = None,
    currencyCode            : str      = "EUR",
    max                     : int      = 50,
    sources : Sequence[str] = ("GDS",),
) -> str:
    """Calls raw POST /v2/shopping/flight‑offers with body you provided."""
    if adults<1 or adults>9: return _json_error("adults 1‑9")

    body = {
        "currencyCode": currencyCode,
        "sources": list(sources),
        "originDestinations":[{
            "id":"1",
            "originLocationCode": originLocationCode.upper(),
            "destinationLocationCode": destinationLocationCode.upper(),
            "departureDateTimeRange": {"date": departureDate},
        }],
        "travelers":[{"id":str(i+1),"travelerType":"ADULT"} for i in range(adults)],
        "searchCriteria":{"maxFlightOffers":max},
    }
    if returnDate:
        body["originDestinations"].append({
            "id":"2",
            "originLocationCode": destinationLocationCode.upper(),
            "destinationLocationCode": originLocationCode.upper(),
            "departureDateTimeRange": {"date": returnDate},
        })

    sess = ctx.request_context.lifespan_context.oauth
    try:
        r = sess.session.post(FLIGHT_URL, json=body, headers=sess.headers(), timeout=30)
        r.raise_for_status()
        return r.text   # already JSON
    except requests.HTTPError as e:
        try: return r.text
        except: return _json_error(str(e))
    except Exception as e:
        return _json_error(f"Unexpected error: {e}")

# ═════════════════════ 🏨 HOTEL TOOLS (SDK) ═══════════════════════════════
# -------- search_hotels_by_city -------------------------------------------
@mcp.tool()
def search_hotels_by_city(
    cityCode:str,
    ctx:Context,
    radius:int=5,
    radiusUnit:str="KM",
    chainCodes:str|None=None,
    amenities:str|None=None,
    ratings:str|None=None,
    hotelSource:str="ALL",
)->str:
    if len(cityCode)!=3 or not cityCode.isalpha():
        return _json_error("cityCode must be 3‑letter IATA")
    sdk=ctx.request_context.lifespan_context.amadeus_sdk
    params={"cityCode":cityCode.upper(),"radius":radius,"radiusUnit":radiusUnit,"hotelSource":hotelSource}
    if chainCodes: params["chainCodes"]=chainCodes
    if amenities : params["amenities"]=amenities
    if ratings   : params["ratings"]=ratings
    try:
        resp=sdk.reference_data.locations.hotels.by_city.get(**params)
        return json.dumps(resp.body)
    except ResponseError as e:
        return _json_error(_stringify(e))
    except Exception as e:
        return _json_error(f"Unexpected error: {e}")

# -------- search_hotels_by_geocode ----------------------------------------
@mcp.tool()
def search_hotels_by_geocode(
    latitude:float,
    longitude:float,
    ctx:Context,
    radius:int=5,
    radiusUnit:str="KM",
    chainCodes:str|None=None,
    amenities:str|None=None,
    ratings:str|None=None,
    hotelSource:str="ALL"
)->str:
    if not(-90<=latitude<=90) or not(-180<=longitude<=180):
        return _json_error("lat/lon out of range")
    sdk=ctx.request_context.lifespan_context.amadeus_sdk
    params={"latitude":latitude,"longitude":longitude,"radius":radius,
            "radiusUnit":radiusUnit,"hotelSource":hotelSource}
    if chainCodes:params["chainCodes"]=chainCodes
    if amenities :params["amenities"]=amenities
    if ratings   :params["ratings"]=ratings
    try:
        resp=sdk.reference_data.locations.hotels.by_geocode.get(**params)
        return json.dumps(resp.body)
    except ResponseError as e:
        return _json_error(_stringify(e))
    except Exception as e:
        return _json_error(f"Unexpected error: {e}")

# -------- autocomplete_hotel_name -----------------------------------------
@mcp.tool()
def autocomplete_hotel_name(
    keyword:str,
    ctx:Context,
    subType:str|Sequence[str]=("HOTEL_LEISURE",),
    countryCode:str|None=None,
    lang:str="EN",
    max:int=20,
)->str:
    if len(keyword)<4: return _json_error("keyword ≥4 chars")
    if isinstance(subType,str): subType=[subType]
    sdk=ctx.request_context.lifespan_context.amadeus_sdk
    params={"keyword":keyword,"subType":subType,"lang":lang,"max":max}
    if countryCode: params["countryCode"]=countryCode.upper()
    try:
        resp=sdk.reference_data.locations.hotel.get(**params)
        return json.dumps(resp.body)
    except ResponseError as e:
        return _json_error(_stringify(e))
    except Exception as e:
        return _json_error(f"Unexpected error: {e}")

# -------- search_hotel_offers ---------------------------------------------
@mcp.tool()
def search_hotel_offers(
    hotelIds:List[str],
    ctx:Context,
    checkInDate:str|None=None,
    checkOutDate:str|None=None,
    adults:int=1,
    roomQuantity:int=1,
    currency:str|None=None,
    priceRange:str|None=None,
    paymentPolicy:str="NONE",
    boardType:str|None=None,
    includeClosed:bool=False,
    bestRateOnly:bool=True,
    countryOfResidence:str|None=None,
)->str:
    if not(1<=len(hotelIds)<=20):
        return _json_error("hotelIds 1‑20")
    sdk=ctx.request_context.lifespan_context.amadeus_sdk
    params={"hotelIds":",".join(hotelIds),"adults":adults,"roomQuantity":roomQuantity,
            "includeClosed":includeClosed,"bestRateOnly":bestRateOnly,
            "paymentPolicy":paymentPolicy}
    if checkInDate : params["checkInDate"]=checkInDate
    if checkOutDate: params["checkOutDate"]=checkOutDate
    if currency    : params["currency"]=currency
    if priceRange  : params["priceRange"]=priceRange
    if boardType   : params["boardType"]=boardType
    if countryOfResidence: params["countryOfResidence"]=countryOfResidence
    try:
        resp=sdk.shopping.hotel_offers_search.get(**params)
        return json.dumps(resp.body)
    except ResponseError as e:
        return _json_error(_stringify(e))
    except Exception as e:
        return _json_error(f"Unexpected error: {e}")

# ─────────────────────────── prompts (unchanged) ───────────────────────────
@mcp.prompt()
def hotel_search_prompt(city:str,check_in:str,check_out:str)->str:
    return f"Find hotels in {city} from {check_in} to {check_out}, sorted by price."

@mcp.prompt()
def flight_search_prompt(origin:str,destination:str,date:str)->str:
    return (f"Search flights {origin} → {destination} on {date}, cheapest first.")

# ─────────────────────────── main ──────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
