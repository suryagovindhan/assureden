import asyncio
import websockets
import json
import uuid
import platform
from agent.executor import AgentExecutor

SERVER_WS_URL = "ws://localhost:8000/ws/agent/"

async def listen_to_server():
    agent_id = str(uuid.uuid4())[:8]
    ws_url = f"{SERVER_WS_URL}agent-{agent_id}"
    
    print(f"Starting Agent {agent_id}. Connecting to {ws_url}...")
    
    executor = AgentExecutor()

    try:
        async with websockets.connect(ws_url) as websocket:
            print("Connected!")
            
            # Send initial host info
            host_info = {
                "os": platform.system(),
                "release": platform.release(),
                "status": "ONLINE"
            }
            await websocket.send(json.dumps({"type": "register", "host_info": host_info}))

            while True:
                message = await websocket.recv()
                print(f"Received JSON Instruction: {message}")
                
                # Execute the instruction
                result = executor.parse_and_execute(message)
                
                # Send back the result
                response = {
                    "type": "result",
                    "data": result
                }
                await websocket.send(json.dumps(response))
                print(f"Sent Result: {result}")
                
    except websockets.exceptions.ConnectionClosed:
        print("Connection to server closed.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(listen_to_server())
