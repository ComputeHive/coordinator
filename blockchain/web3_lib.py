from web3 import Web3
import os

infura_url = os.environ["INFURA_URL"]
address = os.environ["ADDRESS"]
# abi = '[{"constant":true,"inputs":[],"name":"cera","outputs":[{"name":"","type":"address"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[],"name":"terminate","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"getBalance","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"getCera","outputs":[{"name":"","type":"address"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"getStorageNodes","outputs":[{"name":"","type":"address[]"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"A","type":"address"}],"name":"deleteStorageNode","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"getwebUser","outputs":[{"name":"","type":"address"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"webUser","outputs":[{"name":"","type":"address"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[],"name":"userPay","outputs":[],"payable":true,"stateMutability":"payable","type":"function"},{"constant":true,"inputs":[{"name":"","type":"uint256"}],"name":"storageNodes","outputs":[{"name":"","type":"address"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"A","type":"address"},{"name":"payment","type":"uint256"}],"name":"payStorageNode","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":false,"inputs":[{"name":"A","type":"address"}],"name":"addStorageNode","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":false,"inputs":[{"name":"A","type":"address"},{"name":"index","type":"uint256"}],"name":"swapStorageNode","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"},{"inputs":[{"name":"_userValue","type":"uint256"}],"payable":false,"stateMutability":"nonpayable","type":"constructor"}]'
# bytecode = "6060604052341561000f57600080fd5b60405160208061079383398101604052808051600355505060008054600160a060020a033316600160a060020a0319909116179055601960045561073b806100586000396000f300606060405236156100c25763ffffffff7c0100000000000000000000000000000000000000000000000000000000600035041663065ef7a781146100c75780630c08bf88146100f657806312065fe01461010b57806316fb0867146101305780632e67d2591461014357806346a3576a146101a95780634a196f01146101c85780635b13b243146101db57806375f3349d146101ee57806390f0bfb7146101f6578063c083dad01461020c578063cf715b711461022e578063db0de60f1461024d575b600080fd5b34156100d257600080fd5b6100da61026f565b604051600160a060020a03909116815260200160405180910390f35b341561010157600080fd5b61010961027e565b005b341561011657600080fd5b61011e6102d4565b60405190815260200160405180910390f35b341561013b57600080fd5b6100da6102e3565b341561014e57600080fd5b6101566102f2565b60405160208082528190810183818151815260200191508051906020019060200280838360005b8381101561019557808201518382015260200161017d565b505050509050019250505060405180910390f35b34156101b457600080fd5b610109600160a060020a036004351661035a565b34156101d357600080fd5b6100da610483565b34156101e657600080fd5b6100da610492565b6101096104a1565b341561020157600080fd5b6100da600435610518565b341561021757600080fd5b610109600160a060020a0360043516602435610540565b341561023957600080fd5b610109600160a060020a03600435166105f5565b341561025857600080fd5b610109600160a060020a036004351660243561065b565b600054600160a060020a031681565b60005433600160a060020a0390811691161461029957600080fd5b600054600160a060020a039081169030163180156108fc0290604051600060405180830381858888f1935050505015156102d257600080fd5b565b600160a060020a033016315b90565b600054600160a060020a031690565b6102fa6106c0565b600280548060200260200160405190810160405280929190818152602001828054801561035057602002820191906000526020600020905b8154600160a060020a03168152600190910190602001808311610332575b5050505050905090565b6000805433600160a060020a0390811691161461037657600080fd5b5060005b60025481101561047f5781600160a060020a031660028281548110151561039d57fe5b600091825260209091200154600160a060020a03161415610477576002805460001981019081106103ca57fe5b60009182526020909120015460028054600160a060020a0390921691839081106103f057fe5b6000918252602090912001805473ffffffffffffffffffffffffffffffffffffffff1916600160a060020a039290921691909117905560028054600019810190811061043857fe5b6000918252602090912001805473ffffffffffffffffffffffffffffffffffffffff1916905560028054906104719060001983016106d2565b5061047f565b60010161037a565b5050565b600154600160a060020a031690565b600154600160a060020a031681565b60035434116104af57600080fd5b6001805473ffffffffffffffffffffffffffffffffffffffff191633600160a060020a0390811691909117909155600054600454908216916108fc9160649130163102049081150290604051600060405180830381858888f1935050505015156102d257600080fd5b600280548290811061052657fe5b600091825260209091200154600160a060020a0316905081565b6000805433600160a060020a0390811691161461055c57600080fd5b5060005b6002548110156105f05782600160a060020a031660028281548110151561058357fe5b600091825260209091200154600160a060020a031614156105e85760028054829081106105ac57fe5b600091825260209091200154600160a060020a031682156108fc0283604051600060405180830381858888f1935050505015156105e857600080fd5b600101610560565b505050565b60005433600160a060020a0390811691161461061057600080fd5b600280546001810161062283826106d2565b506000918252602090912001805473ffffffffffffffffffffffffffffffffffffffff1916600160a060020a0392909216919091179055565b60005433600160a060020a0390811691161461067657600080fd5b8160028281548110151561068657fe5b6000918252602090912001805473ffffffffffffffffffffffffffffffffffffffff1916600160a060020a03929092169190911790555050565b60206040519081016040526000815290565b8154818355818115116105f0576000838152602090206105f09181019083016102e091905b8082111561070b57600081556001016106f7565b50905600a165627a7a72305820e94a44110b115acac04c6245c44bd552ac09e9d05355cd6c1af250bb3d93ad540029"
abi = []
bytecode = b""
private_key = os.environ["PRIVATE_KEY"]

w3 = Web3(Web3.HTTPProvider(infura_url))
# w3.middleware_onion.inject(geth_poa_middleware, layer=0)
w3.eth.defaultAccount = address


def get_contract(contract_address):
    pay_contract = w3.eth.contract(address=contract_address, abi=abi)
    return pay_contract


def create_contract(payment_limit = 499):
    pay_contract_to_deploy = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.getTransactionCount(w3.eth.defaultAccount)
    transaction = pay_contract_to_deploy.constructor(int(payment_limit)).buildTransaction({
        'gas': 10000000,
        'gasPrice': w3.toWei('10', 'gwei'),
        'from': w3.eth.defaultAccount,
        'nonce': nonce
    })
    # tx_hash = pay_contract_to_deploy.constructor(int(payment_limit)).transact()
    signed_txn = w3.eth.account.signTransaction(transaction, private_key=private_key)
    tx_hash = w3.eth.sendRawTransaction(signed_txn.rawTransaction)
    tx_receipt = w3.eth.waitForTransactionReceipt(tx_hash)
    pay_contract = w3.eth.contract(
        address=tx_receipt.contractAddress,
        abi=abi
    )
    # pay_contract.address for address of the contract
    return pay_contract


def pay_storage_node(contract, storage_address, payment):
    nonce = w3.eth.getTransactionCount(w3.eth.defaultAccount)
    transaction = contract.functions.payStorageNode(str(storage_address), int(payment)).buildTransaction({
        'gas': 1000000,
        'gasPrice': w3.toWei('10', 'gwei'),
        'from': w3.eth.defaultAccount,
        'nonce': nonce
    })
    signed_txn = w3.eth.account.signTransaction(transaction, private_key=private_key)
    tx_hash = w3.eth.sendRawTransaction(signed_txn.rawTransaction)
    w3.eth.waitForTransactionReceipt(tx_hash)


def add_node(contract, storage_address):
    # add storage node
    nonce = w3.eth.getTransactionCount(w3.eth.defaultAccount)
    transaction = contract.functions.addStorageNode(storage_address).buildTransaction({
        'gas': 1000000,
        'gasPrice': w3.toWei('10', 'gwei'),
        'from': w3.eth.defaultAccount,
        'nonce': nonce
    })
    signed_txn = w3.eth.account.signTransaction(transaction, private_key=private_key)
    tx_hash = w3.eth.sendRawTransaction(signed_txn.rawTransaction)
    w3.eth.waitForTransactionReceipt(tx_hash)
    # pay_contract.address for address of the contract
    return True


def delete_node(contract, storage_address):
    nonce = w3.eth.getTransactionCount(w3.eth.defaultAccount)
    transaction = contract.functions.deleteStorageNode(storage_address).buildTransaction({
        'gas': 1000000,
        'gasPrice': w3.toWei('10', 'gwei'),
        'from': w3.eth.defaultAccount,
        'nonce': nonce
    })
    signed_txn = w3.eth.account.signTransaction(transaction, private_key=private_key)
    tx_hash = w3.eth.sendRawTransaction(signed_txn.rawTransaction)
    w3.eth.waitForTransactionReceipt(tx_hash)
    # pay_contract.address for address of the contract
    return True


def swap_nodes(contract, storage_address, index):
    nonce = w3.eth.getTransactionCount(w3.eth.defaultAccount)
    transaction = contract.functions.swapStorageNode(storage_address, index).buildTransaction({
        'gas': 1000000,
        'gasPrice': w3.toWei('10', 'gwei'),
        'from': w3.eth.defaultAccount,
        'nonce': nonce
    })
    signed_txn = w3.eth.account.signTransaction(transaction, private_key=private_key)
    tx_hash = w3.eth.sendRawTransaction(signed_txn.rawTransaction)
    w3.eth.waitForTransactionReceipt(tx_hash)
    return True


def terminate(contract):
    nonce = w3.eth.getTransactionCount(w3.eth.defaultAccount)
    transaction = contract.functions.terminate().buildTransaction({
        'gas': 1000000,
        'gasPrice': w3.toWei('10', 'gwei'),
        'from': w3.eth.defaultAccount,
        'nonce': nonce
    })
    signed_txn = w3.eth.account.signTransaction(transaction, private_key=private_key)
    tx_hash = w3.eth.sendRawTransaction(signed_txn.rawTransaction)
    w3.eth.waitForTransactionReceipt(tx_hash)
    return True


def get_storage_nodes(contract):
    return contract.functions.getStorageNodes().call()


def get_web_user(contract):
    return contract.functions.getwebUser().call()


def get_balance(contract):
    return contract.functions.getBalance().call()


def get_cera(contract):
    return contract.functions.getCera().call()


# this function for testing, it is not gonna be used in backend
def user_pay(contract):
    nonce = w3.eth.getTransactionCount(w3.eth.defaultAccount)
    transaction = contract.functions.userPay().buildTransaction({
        'gas': 100000,
        'gasPrice': w3.toWei('10', 'gwei'),
        'from': w3.eth.defaultAccount,
        'value': 500,
        'nonce': nonce
    })
    signed_txn = w3.eth.account.signTransaction(transaction, private_key=private_key)
    tx_hash = w3.eth.sendRawTransaction(signed_txn.rawTransaction)
    w3.eth.waitForTransactionReceipt(tx_hash)
    return True