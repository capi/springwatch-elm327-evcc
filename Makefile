.PHONY: docker-image
docker-image:
	docker build -t cr.vpn.dont-panic.cc/wican-elm327-evcc-mqtt-dacia:latest .

.PHONY: docker-publish
docker-publish:
	docker push cr.vpn.dont-panic.cc/wican-elm327-evcc-mqtt-dacia:latest
