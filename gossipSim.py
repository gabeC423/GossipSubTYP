#Imports:
import simpy
import random
from config import *

#Global variables:
env = simpy.Environment()
nodes = []
current_block_id = 0
current_node_id = 0
proposer_nodes = []
created_blocks = []

#------------------------------------------------------------------------------------#
                     #MESSAGE CLASSES:
#Message class, defines structure of a message:
class Message:
    def __init__(self, block_id, sender_id, creation_time, height, parent = None):
        #Set parent:
        if parent != None:
            self.parent = parent
        else:
            self.parent = None

        #Message attributes:
        self.block_id = block_id
        self.size = block_size
        self.sender_id = sender_id
        self.creation_time = creation_time
        self.height = height

#'I have' message class:
class IHaveMessage:
    def __init__(self, sender_id, creation_time, advertised_block_id):
        self.sender_id = sender_id
        self.creation_time = creation_time
        self.advertised_block_id = advertised_block_id
        self.size = i_have_want_size

#'I want' message class:
class IWantMessage():
    def __init__(self, sender_id, creation_time, requested_block_id):
        self.sender_id = sender_id
        self.creation_time = creation_time
        self.requested_block_id = requested_block_id
        self.size = i_have_want_size

#------------------------------------------------------------------------------------#
                        #NODE CLASS AND METHODS:
#Node class, defines structure of a node:
class Node:
    def __init__(self, env, initial_end_chain):
        #Set Node ID:
        global current_node_id
        current_node_id += 1

        #Node attributes:
        self.bandwidth = bandwidth
        self.neighbours = []
        self.node_id = current_node_id
        self.inbox = simpy.Store(env)
        self.seen_blocks = set()
        self.log = []
        self.env = env
        self.metrics = {}
        self.end_of_chain_block = initial_end_chain
        self.blocks = {}
        self.chain_ends = set()
        self.peer_degree_met = False
        
        #Add initial block to the chain ends:
        self.chain_ends.add(initial_end_chain)
        env.process(self.run())

    #Method to add a neighbour:
    def add_neighbour(self, neighbour):
        global peer_degree

        #Checks that the amount of neighbours a node has does not exceed the peer degree:
        if len(self.neighbours) < peer_degree:
            #Adds a new neighbour and locally logs this event as successful:
            self.neighbours.append(neighbour)

            #Debug:
            #log_message = self.env.now, "Added new neighbour: " + str(neighbour.node_id)
            #self.log.append(log_message)
        #else:
            #If the peer degree condition is not met then the node locally logs the event as unsuccessful.
            # log_message = self.env.now, "Neighbour list has hit peer degree, could not add node: " + str(neighbour.node_id)
            # self.log.append(log_message)

    #Run method:
    def run(self):
        while True:
            message = yield self.inbox.get()

            if isinstance(message, Message):
                #Checks that the node has not already received this block:
                if message.block_id not in self.seen_blocks and (message.parent is None or message.parent in self.blocks.values()):
                    #Marks block as seen, now that it has received it:
                    self.seen_blocks.add(message.block_id)
                    self.blocks[message.block_id] = message

                    #Create 'I have' message for the received block:
                    i_have_message = IHaveMessage(self.node_id, self.env.now, message.block_id)
                    self.env.process(self.send_message(i_have_message))
                    
                    #Debug:
                    # #Locally logs that an 'I have' message was sent to all neighbours:
                    # log_message = self.env.now, "'I have' message for block: " + str(i_have_message.advertised_block_id) + " was sent to all neighbours."
                    # self.log.append(log_message)

                    #Checks if the block's parent exists and is an end of a chain:
                    if message.parent is not None:
                        self.chain_ends = {end for end in self.chain_ends if end.block_id != message.parent.block_id}

                    #Set current block as new chain end:
                    self.chain_ends.add(message)

                    # #Debug:
                    # #Locally logs this event as successful:
                    # log_message = self.env.now, "Received block: " + str(message.block_id)
                    # self.log.append(log_message)
                    
                    #Locally Records the time the node received the block:
                    self.metrics[message.block_id] = self.env.now
                    
                #Debug:
                # elif message.parent is not None and message.parent not in self.blocks.values():
                #     log_message = "Block: " + str(message.block_id) + " is an orphan, message discarded."
                #     self.log.append(log_message)
                #Debug:
                # else:
                #     #If block has already been received, node locally logs this event as unsucessful:
                #     log_message = self.env.now, "Block has already been received by this node: " + str(message.block_id)
                #     self.log.append(log_message)
            #Handles if the received message is of type: 'I have':
            elif isinstance(message, IHaveMessage):
                #Debug:
                # #Locally logs that this node received an 'I have' message:
                # log_message = self.env.now, "'I have' message received from node: " + str(message.sender_id)
                # self.log.append(log_message)

                #Decides whether the node wants to request the advertised block, this is decided by whether it has seen the advertised block before:
                if message.advertised_block_id not in self.seen_blocks:
                    i_want_message = IWantMessage(self.node_id, self.env.now, message.advertised_block_id)
                    recipient = self.get_node_from_id(message.sender_id)
                    
                    #Sends the 'I want' message:
                    if recipient is not None:
                        yield self.env.process(self.send_message(i_want_message, recipient))

                        #Debug:
                        # #Locally logs that this node has sent an 'I have' message to the node who sent the 'I want' message:
                        # log_message = self.env.now, "'I want' message sent to: " + str(message.sender_id)
                        # self.log.append(log_message)
            #Handles if the received message is of type: 'I want':
            elif isinstance(message, IWantMessage):
                #Debug:
                # #Locally logs that this node received an 'I want' message:
                # log_message = self.env.now, "'I want' message received from node: " + str(message.sender_id)
                # self.log.append(log_message)

                if message.requested_block_id in self.blocks:
                    requested_block = self.blocks[message.requested_block_id]
                    recipient = self.get_node_from_id(message.sender_id)

                    if recipient is not None:
                        yield self.env.process(self.send_message(requested_block, recipient))

                        #Locally logs the sending of the requested block to the node requesting it:
                        log_message = self.env.now, "Requested block sent to node: " + str(message.sender_id)
                        self.log.append(log_message)
                    
    #Get a node from its ID:
    def get_node_from_id(self, node_id):
        for node in nodes:
            if node.node_id == node_id:
                return node
        return None
    
    #Helper method for sendning a block to a single node:
    def send_single_node_message(self, message, neighbour):
        #Calculates send delay:
        send_delay = message.size / self.bandwidth

        yield neighbour.env.timeout(send_delay)
        yield neighbour.inbox.put(message)

    def create_block(self):
        global current_block_id
        #Stores current longest chain end:
        current_best_end = None

        #Finds the chain end of the longest chain (best chain):
        for end in self.chain_ends:
            if current_best_end == None or end.height > current_best_end.height:
                current_best_end = end
        
        current_block_id += 1

        #Creates block and sets it's parent as the best chain end:
        block = Message(current_block_id, self.node_id, self.env.now, current_best_end.height + 1, current_best_end)

        #Create 'I have' for created block:
        i_have_message = IHaveMessage(self.node_id, self.env.now, block.block_id)
        self.env.process(self.send_message(i_have_message))

        #Locally logs that an 'I have' message was sent to all neighbours:
        log_message = self.env.now, "'I have' message for block: " + str(i_have_message.advertised_block_id) + " was sent to all neighbours."
        self.log.append(log_message)

        self.end_of_chain_block = block
        self.seen_blocks.add(block.block_id)
        self.blocks[block.block_id] = block
        self.chain_ends.remove(current_best_end)
        self.chain_ends.add(block)

        #Locally log creation of block:
        log_message = self.env.now, "Created block: " + str(block.block_id)
        self.log.append(log_message)
        
        #Update metrics:
        self.metrics[block.block_id] = self.env.now
        self.env.process(self.send_message(block))

        return block
    
    #Method for sending blocks and messages:
    #Chat GPT helped with this function.
    def send_message(self, message, recipient_id = None):
        active_nodes = []
        queue = list(self.neighbours)

        if recipient_id == None:
            while queue or active_nodes:
                while len(active_nodes) < max_parallel_nodes and queue:
                    neighbour = queue.pop(0)
                    process = self.env.process(self.send_single_node_message(message, neighbour))
                    active_nodes.append(process)

                if active_nodes:
                    yield simpy.events.AnyOf(self.env, active_nodes)

                active_nodes = [p for p in active_nodes if not p.triggered]
        else:
            yield self.env.process(self.send_single_node_message(message, recipient_id))

#------------------------------------------------------------------------------------#
                    #PROGRAM FUNCTIONS:
        
def instantiate_nodes():
    for i in range(number_of_nodes):
        new_node = Node(env, start_block)
        new_node.blocks[start_block.block_id] = start_block
        nodes.append(new_node)

#Creates network layout for nodes:
def create_topology():
    for node in nodes:
        available_nodes = []

        #Ensures that available nodes to be added as neighbours have not already met peer degree:
        for n in nodes:
            if n.peer_degree_met == False and n != node:
                available_nodes.append(n)

        #Prevent infinite loop if not enough available nodes
        while len(node.neighbours) < peer_degree and available_nodes:  

            proposed_peer = random.choice(available_nodes)
            available_nodes.remove(proposed_peer)

            node.add_neighbour(proposed_peer)

            #Make connection bidirectional so both nodes count the neighbour
            proposed_peer.add_neighbour(node)  
        
        #Checks if peer degree is met:
        if len(node.neighbours) >= peer_degree:
            node.peer_degree_met = True

        #Locally logs that neighbour was added:
        log_message = node.env.now, "Added neighbours: " +str([n.node_id for n in node.neighbours])
        node.log.append(log_message)

#Calculates consensus for a block:
def calculate_consenus_time(block):
    highest_time = None
    consensus_met = True
    consensus_time = None
    nodes_met = 0
    
    for node in nodes:
        current_depth = 0
        current_greatest_end = None

        #Checks each fork:
        for end in node.chain_ends:
            if current_greatest_end == None:
                current_greatest_end = end
            #Checks to see which is longest chain:
            elif end.height > current_greatest_end.height:
                current_greatest_end = end
        
        current_ancestor = current_greatest_end

        #Traverses chain:
        while current_ancestor != None:
            if current_ancestor.block_id != block.block_id:
                #Increments depth:
                current_depth += 1

                if current_ancestor.parent != None:
                    current_ancestor = current_ancestor.parent
                #Break out of loop if chain has fully been traversed:
                else:
                    consensus_met = False
                    break
            #Consensus is met if confirmation depth is satisfied:
            elif current_ancestor == block:
                if current_depth >= confirmation_depth:
                    #Amount of nodes met consensus is incremented:
                    nodes_met += 1

                #Update new highest time:
                if highest_time is None or node.metrics[block.block_id] > highest_time:
                    highest_time = node.metrics[block.block_id]

                #Exit loop:
                break
            
    #Calculate time consensus was met:
    if nodes_met /len(nodes) >= 0.51:
        consensus_time = highest_time - block.creation_time
    #'None' output used to determine that consensus was not met:
    else:
        consensus_time = None
    
    return consensus_time

#Calculates how many forks there are in the simulation:
def get_number_forks():
    forks = set()

    #Finds forks in each node:
    for node in nodes:
        for end in node.chain_ends:
            forks.add(end.block_id)

    return len(forks) - 1

#Function allowing for repeated dynamic selection of proposal nodes:
def dynamic_node_proposal():
    while True:
        #Waits to propose new node after each interval:
        yield env.timeout(proposal_interval)

        #Randomly slects mode and adds its block to created blocks array:
        for node in nodes:
            if random.random() < proposer_probability:
                created_blocks.append(node.create_block())
                
#------------------------------------------------------------------------------------#               
                            #INITIALISATION:
#Genesis block:
start_block = Message(current_block_id, sender_id = None, creation_time = 0, height = 0, parent = None)

#Set up network:
instantiate_nodes()
create_topology()

#Periodically create proposer nodes:
env.process(dynamic_node_proposal())

#Start simulation:
env.run(until = simulation_time)

#Display node logs:
for node in nodes:
    print(f"Node {node.node_id} log:")
    for entry in node.log:
        print(entry)
    print()

#Calculate consensus time:
for block in created_blocks:
    consensus_time = calculate_consenus_time(block)

    #Consensus output:
    if consensus_time == None:
        print("BLOCK: " + str(block.block_id) + "CONSENSUS WAS NOT MET BEFORE DEADLINE.")
    elif consensus_time > consensus_deadline:
        print("BLOCK: " + str(block.block_id) + "CONSENSUS MET BUT DEADLINE EXCEEDED BY: " + str(consensus_time - consensus_deadline))
    elif consensus_time == consensus_deadline:
        print("BLOCK: " + str(block.block_id) + "CONSENSUS DEADLINE MET.")
    else:
        print("BLOCK: " + str(block.block_id) + "CONSENSUS ACHIEVED BEFORE DEADLINE, TIME REMAINING BEFORE DEADLINE: " + str(consensus_deadline - consensus_time))

#Shows number of forks in simulation:
print("Number of forks in network: " + str(get_number_forks()))
