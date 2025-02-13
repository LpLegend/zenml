Hello there! This is the repository for ZenML. If you would like to see the published 
pip package can be found [here](https://pypi.org/project/zenml).

ZenML is a platform that lets you create machine learning pipelines for production use-cases.
Our [website](https://zenml.io) gives an overview of the features of ZenML and if you find 
it interesting, you can sign up for an early access [here](https://zenml.io/#early-access). You can also learn 
more about how to use ZenML [here](https://docs.zenml.io).

## How to install from pip

You can easily install `zenml` using pip:
```bash
pip install zenml
```

To install an integration, use the pattern:

```bash
pip install zenml[INTEGRATION]
```

e.g.
```bash
pip install zenml[pytorch]
```

Use the keyword `all` in the square brackets if you would like to install all integrations.

## How to install from source
On the other hand, if you like to install from the source directly, you can follow:
```bash
make venv
source venv/bin/activate
make install
make build
```

Note: This will install all integrations!

## Known errors in installation
If you run into a `psutil` error, please install the python-dev libraries:

```bash
sudo apt update
sudo apt install python3.x-dev
```

## Enabling auto completion on the CLI

For Bash, add this to ~/.bashrc:
```bash
eval "$(_zenml_COMPLETE=source_bash zenml)"
```

For Zsh, add this to ~/.zshrc:
```bash
eval "$(_zenml_COMPLETE=source_zsh zenml)"
```

For Fish, add this to ~/.config/fish/completions/foo-bar.fish:
```bash
eval (env _zenml_COMPLETE=source_fish zenml)
```

## Authors

* **ZenML GmbH** - [Company Website](https://zenml.io) - [Product Website](https://zenml.io) - [ZenML Docs](https://docs.zenml.io)