class Settings:
    # bigscreen
    prometheus_query_url = 'http://172.20.53.200:80/api/v1/'
    metrics_fetch_interval = 300
    memcached_address = '10.220.56.19:11211'
    memcached_key_prefix = 'bigscreen_metrics_'

settings = Settings()
