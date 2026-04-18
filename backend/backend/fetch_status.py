import requests
import json
from pyspark.sql.functions import col, current_timestamp, unix_timestamp, lit
from datetime import datetime, timedelta


def get_flight_data(flight_iata):
    """Fetches flight data from Aviationstack API for a specific IATA code."""
    api_key = "88be107ee92399b9fe605291a89d23f7"
    url = "https://api.aviationstack.com/v1/flights"
    
    params = {
        "access_key": api_key,
        "flight_iata": flight_iata
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for {flight_iata}: {e}")
        return None
    
# Read flights where last_check is >= 10 minutes old (changed from 1 hour for testing)
flights_to_update = spark.sql("""
    SELECT 
        flight_number,
        user_id,
        initial_departure_time,
        delay,
        raw_data,
        last_check
    FROM workspace.default.flights
    WHERE 
        last_check IS NULL 
        OR LEAST(
            unix_timestamp(current_timestamp()) - unix_timestamp(last_check),
            unix_timestamp(current_timestamp()) - unix_timestamp(initial_departure_time)
        ) >= 3600
""")

flight_count = flights_to_update.count()
print(f"Found {flight_count} flights that need updating (threshold: 60 minutes)")

if flight_count > 0:
    display(flights_to_update)


# Process each flight and update the table
successful_updates = 0
failed_updates = 0
update_log = []

if flight_count > 0:
    flights_list = flights_to_update.collect()
    
    for flight_row in flights_list:
        flight_number = flight_row.flight_number
        print(f"\nProcessing flight: {flight_number}...")
        
        # Call API
        api_response = get_flight_data(flight_number)
        
        if api_response and api_response.get("data") and len(api_response["data"]) > 0:
            # Extract delay and full JSON
            departure_data = api_response["data"][0].get("departure", {})
            new_delay = departure_data.get("delay")
            
            # Convert full response to JSON string
            raw_json_string = json.dumps(api_response)
            
            # Handle None delay
            if new_delay is None:
                new_delay = 0
                print(f"  -> No delay information, setting delay to 0")
            else:
                print(f"  -> Delay: {new_delay} minutes")
            
            # Escape single quotes for SQL by doubling them
            escaped_json = raw_json_string.replace("'", "''")
            
            # Update the table using SQL
            try:
                spark.sql(f"""
                    UPDATE workspace.default.flights
                    SET 
                        delay = {new_delay},
                        raw_data = '{escaped_json}',
                        last_check = current_timestamp()
                    WHERE flight_number = '{flight_number}'
                """)
                

                
                successful_updates += 1
                update_log.append({"flight": flight_number, "status": "success", "delay": new_delay})
                print(f"  -> ✓ Updated successfully")
                
            except Exception as e:
                failed_updates += 1
                update_log.append({"flight": flight_number, "status": "failed", "error": str(e)})
                print(f"  -> ✗ Update failed: {e}")
        else:
            failed_updates += 1
            update_log.append({"flight": flight_number, "status": "no_data", "error": "No API data available"})
            print(f"  -> ✗ No active flight data found")
    
    print(f"\n{'='*60}") 
    print(f"Update Summary:")
    print(f"  Total flights processed: {flight_count}")
    print(f"  Successful updates: {successful_updates}")
    print(f"  Failed updates: {failed_updates}")
    print(f"{'='*60}")
else:
    print("No flights need updating at this time (threshold: 60 minutes).")
