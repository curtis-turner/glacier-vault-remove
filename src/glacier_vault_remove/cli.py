#!/usr/bin/env python

# -*- coding: UTF-8 -*-

"""
import sys
import json
import time
import os
"""

# import boto3
import click
from loguru import logger

"""
def get_glacier_client():
	os.environ['AWS_DEFAULT_REGION'] = region_name

	# Load credentials
	try:
		f = open('credentials.json', 'r')
		config = json.loads(f.read())
		f.close()

		os.environ['AWS_ACCESS_KEY_ID'] = config['AWSAccessKeyId']
		os.environ['AWS_SECRET_ACCESS_KEY'] = config['AWSSecretKey']

	except:
		logger.error('Cannot load "credentials.json" file... Assuming Role Authentication.')

	sts_client = boto3.client("sts")
	account_id = sts_client.get_caller_identity()["Account"]
	logger.info(f"Working on AccountID: {account_id}")

	try:
		logger.info('Connecting to Amazon Glacier...')
		glacier = boto3.client('glacier')
	except:
		print_exception()
		sys.exit(1)


def split_list(alist, wanted_parts=1):
	length = len(alist)
	return [ alist[i*length // wanted_parts: (i+1)*length // wanted_parts] 
		for i in range(wanted_parts) ]


def process_archive(archive_list):
	logger.info('Starting work on %s items', len(archive_list))
	for index, archive in enumerate(archive_list):
		if archive['ArchiveId'] != '':
			logger.info('%s Remove archive number %s of %s, ID : %s', os.getpid(), index + 1, len(archive_list), archive['ArchiveId'])
			try:
				glacier.delete_archive(
				    vaultName=vaultName,
				    archiveId=archive['ArchiveId']
				)
			except:
				print_exception()

				logger.info('Sleep 2s before retrying...')
				time.sleep(2)

				logger.info('Retry to remove archive ID : %s', archive['ArchiveId'])
				try:
					glacier.delete_archive(
					    vaultName=vaultName,
					    archiveId=archive['ArchiveId']
					)
					logger.info('Successfully removed archive ID : %s', archive['ArchiveId'])
				except:
					logger.error('Cannot remove archive ID : %s', archive['ArchiveId'])


def print_exception():
	exc_type, exc_value = sys.exc_info()[:2]
	logger.error('Exception "%s" occured with message "%s"', exc_type.__name__, exc_value)


def get_jobs(glacier, vaultName):
	try:
		response = glacier.list_jobs(vaultName=vaultName)
		jobs_list = response.get('JobList')
		while response.get('Marker') is not None:
			response = glacier.list_jobs(vaultName=vaultName, marker=response['Marker'])
			jobs_list += response.get('JobList')

		return jobs_list
	except:
		print_exception()
		return []


@click.command()
@click.option("vault_name", "-v")
def remove_vault(region_name: str = "", vault_name: str = "", processes: int = 1, retriaval_job: str = "LATEST"):
	# 3rd argument - log level, num process or job ID
	if len(sys.argv) >= 4:
		if sys.argv[3] == 'DEBUG':
			logger.info('logger level set to DEBUG.')
			logger.getLogger().setLevel(logger.DEBUG)
		elif sys.argv[3].isdigit():
			numProcess = int(sys.argv[3])
		else:
			retrievalJob = sys.argv[3]

	# 4th argument - num process or job ID
	if len(sys.argv) >= 5:
		if sys.argv[4].isdigit():
			numProcess = int(sys.argv[4])
		else:
			retrievalJob = sys.argv[4]

	logger.info('Running with %s processes', numProcess)

	# 5th argument - job ID
	if len(sys.argv) >= 6:
		retrievalJob = sys.argv[5]


	if vaultName == 'LIST':
		try:
			logger.info('Getting list of vaults...')
			response = glacier.list_vaults()
			vault_list = response.get('VaultList')
			while response.get('Marker') is not None:
				response = glacier.list_vaults(marker=response['Marker'])
				vault_list += response.get('VaultList')
		except:
			print_exception()
			sys.exit(1)

		for vault in vault_list:
			logger.info(vault['VaultName'])

		exit(0)

	if retrievalJob == 'LIST':
		logger.info('Getting list of inventory retrieval jobs...')
		jobs_list = get_jobs(vaultName)

		for job in jobs_list:
			if job['Action'] == 'InventoryRetrieval':
				logger.info("{id} - {date} - {status}".format(id=job['JobId'], date=job['CreationDate'], status=job['StatusCode']))

		exit(0)

	try:
		logger.info('Getting selected vault... [{v}]'.format(v=vaultName))
		vault = glacier.describe_vault(vaultName=vaultName)
		logger.info("Working on ARN {arn}".format(arn=vault['VaultARN']))
	except:
		print_exception()
		sys.exit(1)

	if retrievalJob == 'LATEST':
		logger.info('Looking for the latest inventory retrieval job...')
		jobs_list = get_jobs(vaultName) # Reversed to get the latest, not the first
		retrievalJob = ''

		# Check if a job already exists
		for job in jobs_list:
			if job['Action'] == 'InventoryRetrieval':
				logger.info('Found existing job...')
				retrievalJob = job['JobId']
				break
		
		if retrievalJob == '':
			logger.info('No existing job found...')

	if retrievalJob == '' or retrievalJob == 'NEW':
		logger.info('Initiate inventory retrieval...')
		try:
			glacier_resource = boto3.resource('glacier')
			vault = glacier_resource.Vault(accountId, vaultName)
			job = vault.initiate_inventory_retrieval()

			retrievalJob = job.id
		except:
			print_exception()
			sys.exit(1)

	logger.info('Job ID : %s', retrievalJob)

	# Get job status
	job = glacier.describe_job(vaultName=vaultName, jobId=retrievalJob)

	logger.info('Job Creation Date: {d}'.format(d=job['CreationDate']))

	while job['StatusCode'] == 'InProgress':
		# Job are usualy ready within 4hours of request.
		logger.info('Inventory not ready, sleep for 10 mins...')

		time.sleep(60*10)

		job = glacier.describe_job(vaultName=vaultName, jobId=retrievalJob)

	if job['StatusCode'] == 'Succeeded' and __name__ == '__main__':
		logger.info('Inventory retrieved, parsing data...')
		job_output = glacier.get_job_output(vaultName=vaultName, jobId=job['JobId'])
		inventory = json.loads(job_output['body'].read().decode('utf-8'))

		archiveList = inventory['ArchiveList']

		logger.info('Removing %s archives... please be patient, this may take some time...', len(archiveList));
		archiveParts = split_list(archiveList, numProcess)
		jobs = []

		for archive in archiveParts:
			p = Process(target=process_archive, args=(archive,))
			jobs.append(p)
			p.start()

		for j in jobs:
			j.join()

		logger.info('Removing vault...')
		try:
			glacier.delete_vault(
				vaultName=vaultName
			)
			logger.info('Vault removed.')
		except:
			print_exception()
			logger.error('We cant remove the vault now. Please wait some time and try again. You can also remove it from the AWS console, now that all archives have been removed.')

	else:
		logger.info('Vault retrieval failed.')
"""


@click.group()
@click.option("--debug", "-d", is_flag=True, help="turn on debug logging")
def cli(debug: bool = False):
	logger.debug("cli group")
	# glacier = get_glacier_client()
	# remove_vault(glacier)


@cli.group()
def vault(debug: bool = False):
	logger.debug("vault group")


@vault.command(name="list")
def vault_list(debug: bool = False):
	logger.debug("vault list")


@cli.group()
def archive(debug: bool = False):
	logger.debug("archive group")


@archive.command(name="list")
def archive_list():
	logger.debug("arhive list")


if __name__ == "__main__":
	cli()
