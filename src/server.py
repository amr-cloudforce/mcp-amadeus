from mcp.server.fastmcp import FastMCP
from amadeus import Client, ResponseError
import os

mcp = FastMCP("amadeus", dependencies=["amadeus", "httpx"])

amadeus = Client(
    client_id=os.environ.get("AMADEUS_API_KEY"),
    client_secret=os.environ.get("AMADEUS_API_SECRET"),
    # Uncomment the line below to switch to production environment
    # hostname='production'
)

@mcp.tool(
    name="search_flight_offers",
    description="Search for flight offers using the Amadeus API",
)
async def search_flight_offers(
    originLocationCode: str,
    destinationLocationCode: str,
    departureDate: str,
    adults: int,
    returnDate: str = None,
    children: int = 0,
    infants: int = 0,
    travelClass: str = None,
    includedAirlineCodes: str = None,
    excludedAirlineCodes: str = None,
    nonStop: str = "false",
    currencyCode: str = None,
    maxPrice: int = None,
    max: int = 250,
):
    """
    Search for flight offers using the Amadeus API.

    Args:
        originLocationCode (str): IATA code of the departure city/airport (e.g., SYD for Sydney).
        destinationLocationCode (str): IATA code of the destination city/airport (e.g., BKK for Bangkok).
        departureDate (str): Departure date in ISO 8601 format (YYYY-MM-DD, e.g., 2023-05-02).
        adults (int): Number of adult travelers (age 12+), must be 1-9.
        returnDate (str, optional): Return date in ISO 8601 format (YYYY-MM-DD), if round-trip is desired.
        children (int, optional): Number of child travelers (age 2-11), default is 0.
        infants (int, optional): Number of infant travelers (age <= 2), default is 0.
        travelClass (str, optional): Travel class (ECONOMY, PREMIUM_ECONOMY, BUSINESS, FIRST).
        includedAirlineCodes (str, optional): Comma-separated IATA airline codes to include (e.g., "6X,7X").
        excludedAirlineCodes (str, optional): Comma-separated IATA airline codes to exclude (e.g., "6X,7X").
        nonStop (str, optional): If true, only non-stop flights are returned, default is false.
        currencyCode (str, optional): ISO 4217 currency code (e.g., EUR for Euro).
        maxPrice (int, optional): Maximum price per traveler, positive integer with no decimals.
        max (int, optional): Maximum number of flight offers to return, default is 250.

    Returns:
        str: JSON response containing flight offers.
    """
    params = {
        "originLocationCode": originLocationCode,
        "destinationLocationCode": destinationLocationCode,
        "departureDate": departureDate,
        "adults": adults,
        "children": children,
        "infants": infants,
        "nonStop": nonStop,
        "max": max,
    }

    if returnDate:
        params["returnDate"] = returnDate
    if travelClass:
        params["travelClass"] = travelClass.upper()
    if includedAirlineCodes:
        params["includedAirlineCodes"] = includedAirlineCodes
    if excludedAirlineCodes:
        params["excludedAirlineCodes"] = excludedAirlineCodes
    if currencyCode:
        params["currencyCode"] = currencyCode
    if maxPrice:
        params["maxPrice"] = maxPrice

    try:
        # Use Amadeus SDK to make the API call
        response = amadeus.shopping.flight_offers_search.get(**params)
        # Return the raw JSON body as a string
        return response.body
    except ResponseError as error:
        # Handle errors gracefully
        raise Exception(f"Amadeus API error: {str(error)}")

if __name__ == "__main__":
   mcp.run()
