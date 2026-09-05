#!/usr/bin/env python
"""Test script to reproduce the anonymous wildcard filter issue."""

import bottle


def test_anonymous_int_filter():
    """Test that an anonymous wildcard filter works correctly."""
    app = bottle.Bottle()
    
    # Define route with anonymous wildcard and int filter
    @app.route('/item/<:int>')
    def get_item(item_id):
        return {'id': item_id}
    
    # Create a simple WSGI request
    environ = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/item/5',
        'wsgi.url_scheme': 'http',
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '8000',
    }
    
    try:
        result = app(environ, lambda s, h: None)
        print(f"Response status: {result.status}")
        print(f"Response body: {result.body}")
        
        if b'500' in str(result):
            print("ERROR: Got 500 Internal Server Error")
            return False
        elif b'"id": 5' in result.body or b"'id': 5" in result.body:
            print("SUCCESS: Route matched correctly!")
            return True
        else:
            print(f"Unexpected response: {result}")
            return False
            
    except Exception as e:
        print(f"Exception occurred: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_named_int_filter():
    """Test that a named int filter works correctly (baseline)."""
    app = bottle.Bottle()
    
    # Define route with named wildcard and int filter
    @app.route('/item/<n:int>')
    def get_item(n):
        return {'id': n}
    
    environ = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/item/5',
        'wsgi.url_scheme': 'http',
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '8000',
    }
    
    try:
        result = app(environ, lambda s, h: None)
        print(f"Named wildcard Response status: {result.status}")
        print(f"Named wildcard Response body: {result.body}")
        
        if b'500' in str(result):
            print("ERROR: Got 500 Internal Server Error")
            return False
        else:
            print("SUCCESS: Named wildcard route matched correctly!")
            return True
            
    except Exception as e:
        print(f"Exception occurred: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("Testing named int filter (baseline)...")
    test_named_int_filter()
    print("\n" + "="*50 + "\n")
    
    print("Testing anonymous int filter...")
    success = test_anonymous_int_filter()
    
    if not success:
        print("\nThe issue is reproduced!")
