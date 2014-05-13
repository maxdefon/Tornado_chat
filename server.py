import logging
import tornado.ioloop
import tornado.web
import os.path
import tornado.escape
import uuid


class MessageBuffer(object):
    def __init__(self):
        self.waiters = set()
        self.cache = []
        self.cache_size = 200

    def wait_for_messages(self, callback, cursor=None):
        if cursor:
            new_count = 0
            for msg in reversed(self.cache):
                if msg["id"] == cursor:
                    break
                new_count += 1
            if new_count:
                callback(self.cache[-new_count:])
                return
        self.waiters.add(callback)

    def cancel_wait(self, callback):
        self.waiters.remove(callback)

    def new_messages(self, messages):
        logging.info("Sending new message to %r listeners", len(self.waiters))
        for callback in self.waiters:
            try:
                callback(messages)
            except:
                logging.error("Error in waiter callback", exc_info=True)
        self.waiters = set()
        self.cache.extend(messages)
        if len(self.cache) > self.cache_size:
            self.cache = self.cache[-self.cache_size:]


global_message_buffer = MessageBuffer()


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        user_json = self.get_secure_cookie("chat_user")
        if not user_json: return None
        return tornado.escape.json_decode(user_json)


class MainHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
         self.render("index.html", messages=global_message_buffer.cache)
          
        
class MessageNewHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        message = {
             "id": str(uuid.uuid4()),
             "from": self.current_user["name"],
             "message": self.get_argument("message"),
        }
        message["html"] = tornado.escape.to_basestring(
            self.render_string("message.html", message=message))
        if self.get_argument("next", None):
           self.redirect(self.get_argument("next"))
        else:
            self.write(message)
        global_message_buffer.new_messages([message])    
            
            
class MessageUpdatesHandler(BaseHandler):
    @tornado.web.authenticated
    @tornado.web.asynchronous
    def post(self):
        cursor = self.get_argument("cursor", None)
        global_message_buffer.wait_for_messages(self.on_new_messages,cursor=cursor)
        

    def on_new_messages(self, messages):
        # Closed client connection
        if self.request.connection.stream.closed():
            return
        self.finish(dict(messages=messages))

    def on_connection_close(self):
        global_message_buffer.cancel_wait(self.on_new_messages)
   


class LoginHandler(BaseHandler):
    def get(self):
        self.render("login.html")
        
    def post(self):
        if self.get_argument("name", None):
           user = user = {"name": self.get_argument("name"),}
           test = self.set_secure_cookie("chat_user",tornado.escape.json_encode(user))
           self.redirect("/")


class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("chat_user")
        self.redirect("/")
        
        
application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/login", LoginHandler),
    (r"/logout", LogoutHandler),
    (r"/message/new", MessageNewHandler),
    (r"/message/updates", MessageUpdatesHandler),    
],
cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
login_url="/login",
template_path=os.path.join(os.path.dirname(__file__), "templates"),
static_path=os.path.join(os.path.dirname(__file__), "static"),
xsrf_cookies=True,
autoreload=True,
)

if __name__ == "__main__":
    application.listen(8888)
    tornado.ioloop.IOLoop.instance().start()
