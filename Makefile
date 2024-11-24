.PHONY: docker-image
docker-image:
	docker build -t cr.vpn.dont-panic.cc/springwatch-elm327-evcc:latest .

.PHONY: docker-publish
docker-publish:
	docker push cr.vpn.dont-panic.cc/springwatch-elm327-evcc:latest
