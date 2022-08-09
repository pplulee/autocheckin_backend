import json
import time

import requests
import schedule
import os

web_url = 'http://localhost:8080/'
web_key = 'key'


class local_docker:
    def __init__(self):
        self.local_list = self.get_local_list()

    def get_parameter(self, id):
        print(f"获取容器{id}的参数")
        result_json = json.loads(requests.get(f"{web_url}/api/get_parameter.php?key={web_key}&id={id}").text)
        return result_json

    def deploy_docker(self, id):
        data = self.get_parameter(id)
        os.system(f"docker run -d --name=autosign_{id} \
        -e username={data['username']} \
        -e password={data['password']} \
        -e webdriver={data['webdriver']} \
        -e tgbot_token={data['tgbot_token']} \
        -e tgbot_chat_id={data['tgbot_chat_id']} \
        -e wxpusher_uid={data['wxpusher_uid']} \
        --log-opt max-size=1m \
        --log-opt max-file=1 \
        --restart=always \
        sahuidhsu/uom_autocheckin")

    def remove_docker(self, id):
        print(f"删除容器{id}")
        os.system(f"docker stop autosign_{id} && docker rm autosign_{id}")

    def get_local_list(self):
        local_list = []
        result = os.popen("docker ps --format \"{{.Names}}\"")
        for line in result.readlines():
            if line.find("autosign_") != -1:
                local_list.append(line.strip().split("_")[1])
        return local_list

    def get_remote_list(self):
        result_json = json.loads(requests.get(f"{web_url}/api/get_list.php?key={web_key}").text)
        print(f"从云端获取到{len(result_json['id_list'])}个容器")
        return result_json['id_list']

    def sync_finish(self):
        requests.get(f"{web_url}/api/sync_finish.php?key={web_key}")

    def sync(self):
        # 处理需要删除的容器（本地存在，云端不存在）
        for id in self.local_list:
            if id not in self.get_remote_list():
                print(f"移除容器{id}")
                self.remove_docker(id)
                self.local_list.remove(id)
        # 处理需要部署的容器（本地不存在，云端存在）
        remote_list = self.get_remote_list()
        for id in remote_list:
            if id not in self.local_list:
                print(f"部署容器{id}")
                self.deploy_docker(id)
                self.local_list.append(id)
        self.sync_finish()


def job():
    print("开始定时任务")
    Local.sync()


def main():
    print("自动签到后端服务启动")
    global Local
    Local = local_docker()
    job()
    schedule.every(10).minutes.do(job)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
