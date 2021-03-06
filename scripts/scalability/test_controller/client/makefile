# test_controller/client/makefile
# ===============================
#
# This file is part of the client-side infrastructure for Server Scalability
# Tests. The client-side is responsible for orchestrating the benchmarking by
# setting up server resources needed for the tests.
#
# What this file does
# -------------------
#
# This makefile knows how to:
#
#   - Start and stop server-side system resource monitoring.
#
#   - Setup server-side resources for tests (user dbs, access tokens and blobs).
#
#   - Orchestrate test runs using the client-side machinery.
#
#   - Generate reports and save test results.
#
# Running tests
# -------------
#
# To run tests, make sure a Test Controller Server is reachable at $(URI) and
# run `make`.


URI   ?= https://giraffe.cdev.bitmask.net:7001
BLOBS ?= 10000
SIZE  ?= 10


#------------------#
# main test target #
#------------------#

test: bench

bench: bench-cpu bench-mem

bench-cpu: start-cpu bench-upload bench-download stop-cpu

bench-mem: start-mem bench-upload bench-download stop-mem

configure-size:
	sed -i -e "s/size=[[:digit:]]\+/size=$(SIZE)/" Blobs.conf

bench-upload: configure-size create-users delete-blobs
	fl-run-bench -f test_Blobs.py Blobs.test_upload
	fl-build-report --html results/blobs-bench.xml

bench-download: configure-size create-users create-blobs
	fl-run-bench -f test_Blobs.py Blobs.test_download
	fl-build-report --html results/blobs-bench.xml

# for quick tests only
bench-upload-quick: configure-size create-users delete-blobs
	fl-run-bench -c 1 --duration 10 -f test_Blobs.py Blobs.test_upload

# for quick tests only
bench-download-quick: configure-size create-users create-blobs
	fl-run-bench -c 1 --duration 10 -f test_Blobs.py Blobs.test_download

#---------------------#
# resource monitoring #
#---------------------#

start-cpu:
	curl -X POST $(URI)/cpu

stop-cpu:
	curl -X GET $(URI)/cpu

start-mem:
	curl -X POST $(URI)/mem

stop-mem:
	curl -X GET $(URI)/mem


#--------------#
# server setup #
#--------------#

create-users:
	curl -X POST $(URI)/users?create=1

delete-blobs:
	curl -X POST "$(URI)/blobs?action=delete"

create-blobs:
	curl -X POST "$(URI)/blobs?action=create&size=$(SIZE)&amount=$(BLOBS)"
