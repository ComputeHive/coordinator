import json
import os
from web3 import Web3

infura_url = os.environ["INFURA_URL"]
address    = os.environ["ADDRESS"]
private_key = os.environ["PRIVATE_KEY"]

w3 = Web3(Web3.HTTPProvider(infura_url))
w3.eth.default_account = address  # updated: defaultAccount is deprecated in web3.py v6+


def load_contract_artifacts(file_path: str):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["abi"], data["bytecode"]


abi, bytecode = load_contract_artifacts("StorageEscrowVault.json")


def _build_and_send(transaction: dict) -> bool:
    """Sign and broadcast a transaction, wait for receipt."""
    signed = w3.eth.account.sign_transaction(transaction, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)
    return True


def _base_tx(extra: dict | None = None) -> dict:
    """Common transaction fields."""
    tx = {
        "gas": 1_000_000,
        "gasPrice": w3.to_wei("10", "gwei"),
        "from": address,
        "nonce": w3.eth.get_transaction_count(address),
    }
    if extra:
        tx.update(extra)
    return tx


# ── Deployment ────────────────────────────────────────────────────────────────

def create_contract(minimum_deposit: int = 499):
    """Deploy a new StorageEscrowVault and return the bound contract object."""
    factory = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = factory.constructor(minimum_deposit).build_transaction(_base_tx({"gas": 10_000_000}))
    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return w3.eth.contract(address=receipt.contractAddress, abi=abi)


def get_contract(contract_address: str):
    return w3.eth.contract(address=contract_address, abi=abi)


# ── Host registry ─────────────────────────────────────────────────────────────

def add_node(contract, host_address: str) -> bool:
    """Register a new storage host (registerHost)."""
    tx = contract.functions.registerHost(host_address).build_transaction(_base_tx())
    return _build_and_send(tx)


def delete_node(contract, host_address: str) -> bool:
    """Evict a host via swap-and-pop (evictHost)."""
    tx = contract.functions.evictHost(host_address).build_transaction(_base_tx())
    return _build_and_send(tx)


def swap_nodes(contract, replacement_address: str, slot: int) -> bool:
    """Overwrite a registry slot with a different host (replaceHostAt)."""
    tx = contract.functions.replaceHostAt(replacement_address, slot).build_transaction(_base_tx())
    return _build_and_send(tx)


# ── Payments ──────────────────────────────────────────────────────────────────

def pay_storage_node(contract, host_address: str, amount_wei: int) -> bool:
    """Disburse funds from the vault to a registered host (disburseToHost)."""
    tx = contract.functions.disburseToHost(host_address, amount_wei).build_transaction(_base_tx())
    return _build_and_send(tx)


def terminate(contract) -> bool:
    """Drain remaining vault balance to the coordinator (liquidate)."""
    tx = contract.functions.liquidate().build_transaction(_base_tx())
    return _build_and_send(tx)


# ── Read-only queries ─────────────────────────────────────────────────────────

def get_storage_nodes(contract) -> list[str]:
    return contract.functions.fetchAllHosts().call()


def get_depositor(contract) -> str:
    """Replaces getwebUser — returns the address that funded the vault."""
    return contract.functions.fetchDepositor().call()


def get_balance(contract) -> int:
    return contract.functions.fetchVaultBalance().call()


def get_coordinator(contract) -> str:
    return contract.functions.fetchCoordinator().call()


def get_host_count(contract) -> int:
    return contract.functions.fetchHostCount().call()


# ── Testing helper ────────────────────────────────────────────────────────────

def user_pay(contract, amount_wei: int = 500) -> bool:
    """Fund the vault as the depositor (depositFunds — payable)."""
    tx = contract.functions.depositFunds().build_transaction(
        _base_tx({"value": amount_wei})
    )
    return _build_and_send(tx)