import time
import json
from queue import Queue
from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

# Global variable to store output streams for different resources
output_streams = {}

def get_stream_id(resource):
    """Generate a unique ID for the resource operation stream"""
    return f"{resource}_{int(time.time())}"

def generate_sse_message(data, event="message"):
    """Format data as SSE message"""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

@csrf_exempt
def stream_output(request):
    """Endpoint to stream Terraform output via Server-Sent Events"""
    stream_id = request.GET.get('stream_id')
    
    if not stream_id or stream_id not in output_streams:
        def error_stream():
            yield generate_sse_message({"error": "Invalid stream ID"}, "error")
        return StreamingHttpResponse(error_stream(), content_type='text/event-stream')
    
    def event_stream():
        try:
            # Send initial connection message
            yield generate_sse_message({"message": "Connected to output stream"}, "connected")
            
            # Get the output queue for this stream
            output_queue = output_streams[stream_id]["queue"]
            
            while True:
                if not output_queue.empty():
                    message = output_queue.get()
                    
                    # Check if this is the end message
                    if message is None:
                        yield generate_sse_message({"message": "Operation completed"}, "complete")
                        break
                    
                    # Normal output message
                    yield generate_sse_message({"message": message}, "output")
                else:
                    # Check if the process has finished
                    if not output_streams[stream_id]["active"]:
                        yield generate_sse_message({"message": "Operation completed"}, "complete")
                        break
                    time.sleep(0.1)
                    
            # Clean up the stream after it's done
            if stream_id in output_streams:
                del output_streams[stream_id]
                
        except Exception as e:
            yield generate_sse_message({"error": str(e)}, "error")
    
    return StreamingHttpResponse(event_stream(), content_type='text/event-stream')
