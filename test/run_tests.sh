# IMPORTANT: Set the config to use the right socket path

socat -d PTY,link=/tmp/temperature_pts,echo=0 "EXEC:python3 test.py ...,pty,raw",echo=0 &
socat UNIX-LISTEN:/tmp/collectd_sock,fork EXEC:"python3 collectdmock.py"

