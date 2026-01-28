import simpy
import random
from config import *

env = simpy.Environment()
nodes = []
current_block_id = 0
current_node_id = 0

class Message:
    def __init__(self, sender_id):
        global current_block_id
        current_block_id += 1

        self.block_id = current_block_id 
        self.size = block_size
        self.sender_id = sender_id

class Node:
    def __init__(self, env):
        global current_node_id
        current_node_id += 1

        self.bandwidth = bandwidth
        self.neighbours = []
        self.node_id = current_node_id
        self.inbox = simpy.Store(env)
        self.seen_blocks = set()
        self.log = []
        self.env = env
        self.metrics = {}

        env.process(self.run())

    def add_neighbour(self, neighbour):
        global peer_degree

        if len(self.neighbours) < peer_degree:
            self.neighbours.append(neighbour)
            log_message = self.env.now, "Added new neighbour: " + str(neighbour.node_id)
            self.log.append(log_message)
        else:
            log_message = self.env.now, "Neighbour list has hit peer degree, could not add node: " + str(neighbour.node_id)
            self.log.append(log_message)

    def run(self):
        while True:
            block = yield self.inbox.get()
            receive_delay = block.size / self.bandwidth
            yield self.env.timeout(receive_delay)

            if block.block_id not in self.seen_blocks:
                self.seen_blocks.add(block.block_id)

                log_message = self.env.now, "Received block: " + str(block.block_id)
                self.log.append(log_message)

                self.metrics[block.block_id] = self.env.now
                
                self.env.process(self.send_block(block))
            else:
                log_message = self.env.now, "Block has already been received by this node: " + str(block.block_id)
                self.log.append(log_message)
    
    def send_block(self, block):
        for neighbour in self.neighbours:
            send_delay = block.size / self.bandwidth
            yield self.env.timeout(send_delay)
            yield neighbour.inbox.put(block)

    def create_block(self):
        block = Message(self.node_id)
        self.seen_blocks.add(block.block_id)

        log_message = self.env.now, "Created block: " + str(block.block_id)
        self.log.append(log_message)

        self.metrics[block.block_id] = self.env.now

        self.env.process(self.send_block(block))


def instantiate_nodes():
    for i in range(number_of_nodes):
        new_node = Node(env)
        nodes.append(new_node)

def create_topology():
    for node in nodes:
        while len(node.neighbours) < peer_degree:
            proposed_peer = nodes[random.randint(0, number_of_nodes - 1)]

            while proposed_peer in node.neighbours or proposed_peer == node:
                proposed_peer = nodes[random.randint(0, number_of_nodes - 1)]

            node.add_neighbour(proposed_peer)
            log_message = node.env.now, "Added neighbour: " + str(proposed_peer.node_id)
            node.log.append(log_message) 

def calculate_consenus_time(block_id):
    highest_time = None

    for node in nodes:
        if block_id in node.metrics:
            if highest_time is None or node.metrics[block_id] > highest_time:
                highest_time = node.metrics[block_id]

    return highest_time

    
instantiate_nodes()
create_topology()

block_proposer = random.choice(nodes)
block_proposer.create_block()

env.run(until=100)

for node in nodes:
    print(f"Node {node.node_id} log:")
    for entry in node.log:
        print(entry)
    print()
