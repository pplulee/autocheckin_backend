import json
import logging
import os
import time

import requests
import schedule

web_url = ""
web_key = ""


def info(text):
    print("[INFO] " + text)
    logging.info(text)


def error(text):
    print("[ERROR] " + text)
    logging.critical(text)


class local_docker:
    def __init__(self):
        self.local_list = self.get_local_list()

    def get_parameter(self, id):
        info(f"获取容器{id}的参数")
        try:
            result = requests.get(f"{web_url}/api/?action=get_parameter&key={web_key}&id={id}")
            result_json = json.loads(clean_html(result.text))
        except Exception as e:
            error("获取API出错")
            print(e)
            return None
        else:
            if result_json['status'] == "fail":
                error(f"获取容器{id}的参数失败")
                error(result_json['message'])
                return None
        return result_json

    def deploy_docker(self, id):
        data = self.get_parameter(id)
        info(f"部署容器{id}")
        password = data['password'].replace("$", "\$")
        os.system(f"docker run -d --name=autosign_{id} \
        -e username={data['username']} \
        -e password={password} \
        -e webdriver={data['webdriver']} \
        -e tgbot_token={data['tgbot_token']} \
        -e tgbot_userid={data['tgbot_userid']} \
        -e wxpusher_uid={data['wxpusher_uid']} \
        --log-opt max-size=1m \
        --log-opt max-file=1 \
        --restart=always \
        sahuidhsu/uom_autocheckin")

    def remove_docker(self, id):
        info(f"删除容器{id}")
        os.system(f"docker stop autosign_{id} && docker rm autosign_{id}")

    def get_local_list(self):
        local_list = []
        result = os.popen("docker ps --format \"{{.Names}}\"")
        for line in result.readlines():
            if line.find("autosign_") != -1:
                local_list.append(line.strip().split("_")[1])
        info(f"本地存在{len(local_list)}个容器")
        return local_list

    def get_remote_list(self):
        try:
            result = requests.get(f"{web_url}/api/?action=get_list&key={web_key}")
            result_json = json.loads(clean_html(result.text))
        except Exception as e:
            error("获取API出错")
            print(e)
            return self.local_list
        else:
            if result_json['status'] == "fail":
                error(f"获取容器列表失败")
                error(result_json['message'])
                return self.local_list
        result_list = result_json['id_list'].split(",")
        if result_list == ['']:
            result_list = []
        info(f"从云端获取到{len(result_list)}个容器")
        return result_list

    def sync(self):
        info("开始同步")
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
        info("同步完成")


def clean_html(data):
    pointer = len(data) - 1
    while data[pointer] != ">" and pointer > 0:
        pointer -= 1
    return data[pointer:]


def job():
    info("开始定时任务")
    Local.sync()


def main():
    info("自动签到后端服务启动")
    global Local
    Local = local_docker()
    job()
    schedule.every(10).minutes.do(job)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
