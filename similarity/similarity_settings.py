import os
# NOTE: In production and test this file is taken from the deploy repository

# SERVER SETTINGS
INDEX_DIR                   = '/home/fsweb/freesound/freesound-similarity/'
INDEX_NAME                  = 'fs_index'
PRESET_DIR                  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'presets/')
PRESETS                     = ['lowlevel','spectral_centroid'] # 'music'
DEFAULT_PRESET              = "lowlevel"
SIMILARITY_MINIMUM_POINTS   = 2000
LOGFILE                     = '/var/log/freesound/similarity.log'
LISTEN_PORT                 = 8000

# CLIENT SETTINGS (to be moved to django settings?)
SIMILARITY_ADDRESS          = '10.55.0.42'
SIMILARITY_PORT             = 8000

# OTHER
SIMILAR_SOUNDS_TO_CACHE = 100
SIMILARITY_CACHE_TIME = 60*60*1
DEFAULT_NUMBER_OF_RESULTS = 15
