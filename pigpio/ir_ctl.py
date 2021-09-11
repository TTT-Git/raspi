from irrp_m import IRRP

ir = IRRP(file='codes', no_confirm=True)
ir.Playback(GPIO=19, ID='light:on')
ir.stop()