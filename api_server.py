"""
CELESTIAL TRANSIT — Swiss Ephemeris Backend API
Gold-standard planetary calculations with proper timezone + Whole Sign Houses
"""
import swisseph as swe
import json
from datetime import datetime
from timezonefinder import TimezoneFinder
import pytz
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

swe.set_ephe_path(None)  # Moshier ephemeris (built-in, ~1 arcsecond accuracy)

tf = TimezoneFinder()

SIGNS = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo','Libra','Scorpio',
         'Sagittarius','Capricorn','Aquarius','Pisces']
SIGN_GLYPHS = ['♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓']
ELEMENTS = ['fire','earth','air','water','fire','earth','air','water',
            'fire','earth','air','water']

PLANETS = [
    (swe.SUN, 'Sun', '☉'), (swe.MOON, 'Moon', '☽'),
    (swe.MERCURY, 'Mercury', '☿'), (swe.VENUS, 'Venus', '♀'),
    (swe.MARS, 'Mars', '♂'), (swe.JUPITER, 'Jupiter', '♃'),
    (swe.SATURN, 'Saturn', '♄'), (swe.URANUS, 'Uranus', '♅'),
    (swe.NEPTUNE, 'Neptune', '♆'), (swe.PLUTO, 'Pluto', '♇')
]

HOUSE_NAMES = [
    'Self & Appearance', 'Money & Possessions', 'Communication & Siblings',
    'Home & Family', 'Romance & Creativity', 'Health & Daily Work',
    'Partnerships & Marriage', 'Shared Resources & Rebirth',
    'Higher Learning & Travel', 'Career & Public Image',
    'Friends & Wishes', 'Subconscious & Karma'
]

ASPECT_TYPES = [
    {'name': 'Conjunction', 'angle': 0, 'orb': 8, 'symbol': '☌', 'power': 'major'},
    {'name': 'Opposition', 'angle': 180, 'orb': 8, 'symbol': '☍', 'power': 'major'},
    {'name': 'Trine', 'angle': 120, 'orb': 6, 'symbol': '△', 'power': 'major'},
    {'name': 'Square', 'angle': 90, 'orb': 6, 'symbol': '□', 'power': 'major'},
    {'name': 'Sextile', 'angle': 60, 'orb': 4, 'symbol': '⚹', 'power': 'minor'},
]


def lng_to_sign(lng):
    """Convert ecliptic longitude to sign info."""
    si = int(lng / 30)
    deg_in_sign = lng - si * 30
    return {
        'sign': SIGNS[si],
        'glyph': SIGN_GLYPHS[si],
        'degree': int(deg_in_sign),
        'minute': int((deg_in_sign - int(deg_in_sign)) * 60),
        'element': ELEMENTS[si],
        'longitude': round(lng, 4),
        'signIndex': si
    }


def calc_planets(jd_ut):
    """Calculate all planet positions for a given Julian Day (UT)."""
    results = {}
    for pid, name, glyph in PLANETS:
        data, _ = swe.calc_ut(jd_ut, pid)
        lng = data[0]
        speed = data[3]  # daily speed in longitude
        info = lng_to_sign(lng)
        info['name'] = name
        info['glyph'] = glyph
        info['speed'] = round(speed, 4)
        info['retrograde'] = speed < 0
        results[name] = info
    return results


def calc_houses_whole_sign(jd_ut, lat, lon):
    """Calculate Whole Sign Houses using Swiss Ephemeris."""
    cusps, ascmc = swe.houses(jd_ut, lat, lon, b'W')
    asc = ascmc[0]
    mc = ascmc[1]
    
    houses = []
    asc_sign_idx = int(asc / 30)
    for i in range(12):
        sign_idx = (asc_sign_idx + i) % 12
        cusp_lng = sign_idx * 30
        houses.append({
            'number': i + 1,
            'sign': SIGNS[sign_idx],
            'glyph': SIGN_GLYPHS[sign_idx],
            'cusp': cusp_lng,
            'name': HOUSE_NAMES[i],
            'element': ELEMENTS[sign_idx]
        })
    
    return {
        'system': 'Whole Sign',
        'ascendant': lng_to_sign(asc),
        'ascendant_lng': round(asc, 4),
        'midheaven': lng_to_sign(mc),
        'midheaven_lng': round(mc, 4),
        'houses': houses,
        'cusps': [h['cusp'] for h in houses]
    }


def find_aspects(transit_planets, natal_planets):
    """Find all aspects between transit and natal planets."""
    aspects = []
    for t_name, t_info in transit_planets.items():
        for n_name, n_info in natal_planets.items():
            diff = abs(t_info['longitude'] - n_info['longitude'])
            if diff > 180:
                diff = 360 - diff
            for asp in ASPECT_TYPES:
                orb = abs(diff - asp['angle'])
                if orb <= asp['orb']:
                    exactness = round(1 - orb / asp['orb'], 3)
                    aspects.append({
                        'transitPlanet': t_name,
                        'natalPlanet': n_name,
                        'aspect': asp['name'],
                        'symbol': asp['symbol'],
                        'power': asp['power'],
                        'orb': round(orb, 2),
                        'exactness': exactness,
                        'transitLng': t_info['longitude'],
                        'natalLng': n_info['longitude']
                    })
    aspects.sort(key=lambda x: -x['exactness'])
    return aspects


def get_house_for_planet(lng, cusps):
    """Determine which Whole Sign house a planet falls in."""
    for i in range(12):
        start = cusps[i]
        end = cusps[(i + 1) % 12]
        if start < end:
            if start <= lng < end:
                return i + 1
        else:
            if lng >= start or lng < end:
                return i + 1
    return 1


def local_to_utc(year, month, day, hour, minute, lat, lon):
    """Convert local birth time to UTC using timezone database."""
    tz_name = tf.timezone_at(lat=lat, lng=lon)
    if not tz_name:
        tz_name = 'UTC'
    
    tz = pytz.timezone(tz_name)
    local_dt = tz.localize(datetime(year, month, day, hour, minute))
    utc_dt = local_dt.astimezone(pytz.utc)
    
    return {
        'utc_datetime': utc_dt,
        'timezone': tz_name,
        'utc_offset': str(local_dt.utcoffset()),
        'dst_active': bool(local_dt.dst()),
        'utc_hour': utc_dt.hour + utc_dt.minute / 60
    }


def calc_helio_positions(jd_ut):
    """Heliocentric positions for orrery visualization."""
    results = {}
    planet_map = [
        (swe.MERCURY, 'Mercury', 0.387), (swe.VENUS, 'Venus', 0.723),
        (swe.MARS, 'Mars', 1.524), (swe.JUPITER, 'Jupiter', 5.203),
        (swe.SATURN, 'Saturn', 9.537), (swe.URANUS, 'Uranus', 19.19),
        (swe.NEPTUNE, 'Neptune', 30.07), (swe.PLUTO, 'Pluto', 39.48)
    ]
    for pid, name, approx_au in planet_map:
        data, _ = swe.calc_ut(jd_ut, pid, swe.FLG_HELCTR)
        results[name] = {
            'longitude': round(data[0], 4),
            'latitude': round(data[1], 4),
            'distance_au': round(data[2], 4),
            'semi_major_au': approx_au
        }
    # Earth (from Sun's geocentric position + 180°)
    sun_data, _ = swe.calc_ut(jd_ut, swe.SUN)
    earth_lng = (sun_data[0] + 180) % 360
    results['Earth'] = {
        'longitude': round(earth_lng, 4),
        'latitude': 0,
        'distance_au': 1.0,
        'semi_major_au': 1.0
    }
    return results


@app.route('/api/chart', methods=['POST'])
def calculate_chart():
    """Main endpoint: calculate natal chart + current transits."""
    data = request.json
    
    # Birth data
    year = int(data.get('year', 1993))
    month = int(data.get('month', 8))
    day = int(data.get('day', 23))
    hour = int(data.get('hour', 12))
    minute = int(data.get('minute', 0))
    lat = float(data.get('lat', 1.3521))
    lon = float(data.get('lon', 103.8198))
    
    # Convert local time to UTC
    tz_info = local_to_utc(year, month, day, hour, minute, lat, lon)
    utc_dt = tz_info['utc_datetime']
    
    # Julian Day for natal
    jd_natal = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day,
                          utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600)
    
    # Julian Day for now (transits)
    now = datetime.utcnow()
    jd_now = swe.julday(now.year, now.month, now.day,
                        now.hour + now.minute / 60 + now.second / 3600)
    
    # Calculate natal chart
    natal_planets = calc_planets(jd_natal)
    natal_houses = calc_houses_whole_sign(jd_natal, lat, lon)
    
    # Assign houses to natal planets
    cusps = natal_houses['cusps']
    for name, info in natal_planets.items():
        info['house'] = get_house_for_planet(info['longitude'], cusps)
    
    # Calculate transit chart
    transit_planets = calc_planets(jd_now)
    for name, info in transit_planets.items():
        info['house'] = get_house_for_planet(info['longitude'], cusps)
    
    # Aspects
    aspects = find_aspects(transit_planets, natal_planets)
    
    # Heliocentric for orrery
    helio = calc_helio_positions(jd_now)
    
    # Mansion data
    mansion = []
    for h in natal_houses['houses']:
        guests = [
            {'name': name, 'glyph': info['glyph']}
            for name, info in transit_planets.items()
            if info['house'] == h['number']
        ]
        mansion.append({
            'number': h['number'],
            'name': h['name'],
            'sign': h['sign'],
            'glyph': h['glyph'],
            'guests': guests,
            'active': len(guests) > 0
        })
    
    return jsonify({
        'natal': {
            'planets': natal_planets,
            'houses': natal_houses,
            'birth_utc': utc_dt.isoformat(),
            'timezone': tz_info
        },
        'transit': {
            'planets': transit_planets,
            'timestamp': now.isoformat(),
            'julian_day': jd_now
        },
        'aspects': aspects[:20],
        'mansion': mansion,
        'helio': helio,
        'meta': {
            'ephemeris': 'Swiss Ephemeris (Moshier)',
            'house_system': 'Whole Sign',
            'accuracy': '~1 arcsecond'
        }
    })


@app.route('/api/transits', methods=['GET'])
def current_transits():
    """Lightweight endpoint: just current transit positions."""
    now = datetime.utcnow()
    jd_now = swe.julday(now.year, now.month, now.day,
                        now.hour + now.minute / 60 + now.second / 3600)
    
    transit_planets = calc_planets(jd_now)
    helio = calc_helio_positions(jd_now)
    
    return jsonify({
        'planets': transit_planets,
        'helio': helio,
        'timestamp': now.isoformat(),
        'julian_day': jd_now
    })


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'engine': 'Swiss Ephemeris'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
