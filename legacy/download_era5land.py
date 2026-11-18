import cdsapi
import time

client = cdsapi.Client()

# Commented out request for daily statistics over multiple years
# dataset = "derived-era5-land-daily-statistics"
# request = {
#     "variable": ["snow_depth", "2m_temperature", ],
#     "year": [str(y) for y in range(1980, 2025)],
#     "month": "12",
#     "day": ["24", "25", "26"],
#     "daily_statistic": "daily_mean",
#     "time_zone": "utc+00:00",
#     "frequency": "6_hourly",
#     "area": [90, -180, 0, 180]
# }

# target = "era5land_white_christmas_dec24-26_1980-2024.zip"

dataset = "reanalysis-era5-land"

request_base = {
    "variable": [
        "2m_temperature",
        "snow_depth",
        "total_precipitation"
    ],
    "month": "12",
    "day": [
        "10", "11", "12",
        "13", "14", "15",
        "16", "17", "18",
        "19", "20", "21",
        "22", "23", "24",
        "25", "26"
    ],
    "time": [
        "00:00", "01:00", "02:00",
        "03:00", "04:00", "05:00",
        "06:00", "07:00", "08:00",
        "09:00", "10:00", "11:00",
        "12:00", "13:00", "14:00",
        "15:00", "16:00", "17:00",
        "18:00", "19:00", "20:00",
        "21:00", "22:00", "23:00"
    ],
    "data_format": "netcdf",
    "download_format": "zip",
    "area": [90, -180, 0, 180]
}


for year in range(1980, 2025):
    request = request_base.copy()
    request["year"] = str(year)
    target = f"era5land_white_christmas_dec10-26_{year}.zip"
    try:
        client.retrieve(dataset, request, target)
        print(f"Downloaded {target}")
    except Exception as e:
        print(f"Failed to download {year}: {e}")
    time.sleep(1)

client.retrieve(dataset, request, target)