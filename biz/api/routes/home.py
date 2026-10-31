"""
首页路由模块
"""
from flask import Blueprint

home_bp = Blueprint('home', __name__)


@home_bp.route('/')
def home():
    return """<h2>The code review api server is running.</h2>
              <p>Webhook endpoint: <code>/review/webhook</code></p>
              """
