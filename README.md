# Kiro IDE Debian Repository

Easy installation and updates for [Kiro IDE](https://kiro.dev) on Debian and Ubuntu systems.

> Found an issue? Please report it on the [kiro-repo issue tracker](https://github.com/mludvig/kiro-repo/issues).

## What is kiro-repo?

The `kiro-repo` package is a repository configuration package that automatically sets up your system to use the Kiro IDE APT repository. It configures the necessary sources and ensures your system can receive updates for both Kiro IDE and the repository configuration itself.

## Quick Install (Recommended)

This is a two-step process: first install the repository configuration, then install Kiro IDE.

**Step 1:** Download and install repository configuration

```bash
curl -LO https://kiro-repo.aws.nz/kiro-repo.deb
sudo dpkg -i kiro-repo.deb
```

**Step 2:** Update package list and install Kiro IDE

```bash
sudo apt-get update
sudo apt-get install kiro
```

> **Automatic Updates:** The `kiro-repo` package itself will be automatically updated by APT, ensuring your repository configuration stays current. You don't need to manually reinstall it.

## Manual Install

For advanced users who prefer to configure the repository manually:

```bash
# Add repository to sources list
echo "deb [trusted=yes] https://kiro-repo.aws.nz/ /" | sudo tee /etc/apt/sources.list.d/kiro.list

# Update package list and install Kiro IDE
sudo apt-get update
sudo apt-get install kiro
```

## Updating Kiro IDE

Once the repository is configured, you can update Kiro IDE using standard apt commands:

```bash
sudo apt-get update
sudo apt-get upgrade kiro
```
