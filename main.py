import argparse
import json
import logging
import os
import threading
import time

import schedule
from flask import Flask, request
from requests import get

parser = argparse.ArgumentParser(description="")
parser.add_argument("-api_url", help="API URL")
parser.add_argument("-api_key", help="API key")
parser.add_argument("--port", help="interface listen port", default=None, type=int)
parser.add_argument("--token", help="interface token", default=None)
args = parser.parse_args()

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')


class local_docker:
    def __init__(self):
        self.local_list = self.get_local_list()

    def get_parameter(self, id):
        logging.info(f"获取容器{id}的参数")
        try:
            result = get(f"{args.api_url}/api/", data={"action": "get_parameter",
                                                       "key": args.api_key,
                                                       "id": id})
            result_json = json.loads(clean_html(result.text))
        except Exception as e:
            logging.error("获取API出错")
            logging.error(e)
            return None
        else:
            if result_json['status'] == "fail":
                logging.error(f"获取容器{id}的参数失败")
                logging.error(result_json['message'])
                return None
        return result_json

    def deploy_docker(self, id):
        data = self.get_parameter(id)
        if data is None:
            logging.error(f"获取容器{id}的参数失败，跳过部署")
            return
        logging.info(f"部署容器{id}")
        password = data['password'].replace("$", "\$")
        os.system(f"docker run -d --name=autosign_{id} \
        -e username={data['username']} \
        -e password={password} \
        -e webdriver={data['webdriver']} \
        -e tgbot_token={data['tgbot_token']} \
        -e tgbot_userid={data['tgbot_userid']} \
        -e wxpusher_uid={data['wxpusher_uid']} \
        --log-opt max-size=1m \
        --log-opt max-file=2 \
        --restart=on-failure \
        sahuidhsu/uom_autocheckin")

    def remove_docker(self, id):
        logging.info(f"删除容器{id}")
        os.system(f"docker stop autosign_{id} && docker rm autosign_{id}")

    def get_local_list(self):
        local_list = []
        result = os.popen("docker ps -a --format \"{{.Names}}\"")
        for line in result.readlines():
            if line.find("autosign_") != -1:
                local_list.append(line.strip().split("_")[1])
        logging.info(f"本地存在{len(local_list)}个容器")
        return local_list

    def get_remote_list(self):
        try:
            result = get(f"{args.api_url}/api/", data={"action": "get_list",
                                                       "key": args.api_key})
            result_json = json.loads(clean_html(result.text))
        except Exception as e:
            logging.error("获取API出错")
            print(e)
            return self.local_list
        else:
            if result_json['status'] == "fail":
                logging.error(f"获取容器列表失败")
                logging.error(result_json['message'])
                return self.local_list
        result_list = result_json['id_list'].split(",")
        if result_list == ['']:
            result_list = []
        logging.info(f"从云端获取到{len(result_list)}个容器")
        return result_list

    def sync(self):
        logging.info("开始同步")
        self.local_list = self.get_local_list()
        # 处理需要删除的容器（本地存在，云端不存在）
        for id in self.local_list:
            if id not in self.get_remote_list():
                self.remove_docker(id)
                self.local_list.remove(id)
        # 处理需要部署的容器（本地不存在，云端存在）
        remote_list = self.get_remote_list()
        for id in remote_list:
            if id not in self.local_list:
                self.deploy_docker(id)
                self.local_list.append(id)
        logging.info("同步完成")

    def update(self):
        logging.info("开始检查更新")
        self.local_list = self.get_local_list()
        if len(self.local_list) == 0:
            logging.info("没有容器需要更新")
            return
        local_list_str = " ".join(self.local_list)
        os.system(f"docker run --rm \
        -v /var/run/docker.sock:/var/run/docker.sock \
        containrrr/watchtower \
        --cleanup \
        --run-once \
        {local_list_str}")


def update():
    global Local
    Local.update()


def clean_html(data):
    pointer = len(data) - 1
    while data[pointer] != ">" and pointer > 0:
        pointer -= 1
    return data[pointer:]


def job():
    logging.info("开始定时任务")
    Local.sync()


def start_app():
    logging.info("启动后端接口")
    app = Flask(__name__)

    @app.before_request
    def before_request():
        # 检测请求类型是和否为POST
        if request.method != 'POST':
            logging.error("请求类型错误")
            data = {'status': 'fail', 'msg': '请求类型错误'}
            json_data = json.dumps(data).encode('utf-8')
            return app.response_class(json_data, mimetype='application/json')
        if 'token' not in request.headers:
            logging.error("请求头中未包含token")
            print(request.headers)
            data = {'status': 'fail', 'msg': '请求头中未包含token'}
            json_data = json.dumps(data).encode('utf-8')
            return app.response_class(json_data, mimetype='application/json')
        if request.headers['token'] != args.token:
            logging.error("密码错误")
            data = {'status': 'fail', 'msg': 'token错误'}
            json_data = json.dumps(data).encode('utf-8')
            return app.response_class(json_data, mimetype='application/json')

    @app.route('/setTask', methods=['POST'])
    def set_task():
        logging.info("收到设置任务请求")
        if 'id' not in request.form:
            logging.error("缺少任务id")
            data = {'status': 'fail', 'msg': '缺少任务id'}
        else:
            Local.deploy_docker(request.form['id'])
            data = {'status': 'success', 'msg': '设置成功'}
        json_data = json.dumps(data).encode('utf-8')
        return app.response_class(json_data, mimetype='application/json')

    @app.route('/removeTask', methods=['POST'])
    def remove_task():
        logging.info("收到删除任务请求")
        if 'id' not in request.form:
            logging.error("缺少任务id")
            data = {'status': 'fail', 'msg': '缺少任务id'}
        else:
            Local.remove_docker(request.form['id'])
            data = {'status': 'success', 'msg': '删除成功'}
        json_data = json.dumps(data).encode('utf-8')
        return app.response_class(json_data, mimetype='application/json')

    @app.route('/sync', methods=['POST'])
    def sync():
        logging.info("收到同步请求")
        Local.sync()
        data = {'status': 'success', 'msg': '同步成功'}
        json_data = json.dumps(data).encode('utf-8')
        return app.response_class(json_data, mimetype='application/json')

    app.run(host='127.0.0.1', port=args.port)


def main():
    logging.info("自动签到后端服务启动")
    os.system("docker pull sahuidhsu/uom_autocheckin")
    os.system("docker stop $(docker ps -a |  grep \"autosign*\"  | awk '{print $1}')")
    os.system("docker rm $(docker ps -a |  grep \"autosign*\"  | awk '{print $1}')")
    global Local
    Local = local_docker()
    job()
    schedule.every(30).minutes.do(job)
    schedule.every().day.at("00:00").do(update)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    if (args.port is not None) and (args.token is not None):
        thread_app = threading.Thread(target=start_app, daemon=True)
        thread_app.start()
    main()
