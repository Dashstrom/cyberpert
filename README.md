# Cyberpert

## Install

```sh
git clone https://github.com/Dashstrom/cyberpert.git
cd cyberpert
pip3 install .
cyberpert -r requirements-dev.txt
```

## Developement

For setup developpement :

```sh
git clone https://github.com/Dashstrom/cyberpert.git
cd cyberpert
pip3 install -r requirements-dev.txt -r requirements.txt
python3 -m cyberpert
```

For push new features, please process as below :

```sh
black .
isort .
tox
git commit -m "Your amazing feature"
git push
```

## Sources

- [NIST NVD - Common Vulnerabilities and Exposures](https://nvd.nist.gov/vuln/data-feeds#JSON_FEED)
- [NIST NVD - Common Platform Enumerations](https://nvd.nist.gov/feeds/xml/cpe/dictionary/official-cpe-dictionary_v2.3.xml.zip)
- [Google Clound - BigQuery API - The Python Package Index](https://packaging.python.org/en/latest/guides/analyzing-pypi-package-downloads/)

## Warning : Bigquery

Bigquery requirement a google clound account.

Go on [BigQuery API](https://console.cloud.google.com/apis/library/bigquery.googleapis.com) for more details.

Set `GOOGLE_APPLICATION_CREDENTIALS` environnement variable to your credentials path or move your credentials to `creds.json`.
