#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
    Kullanım : wls_manager.py <manage_what> <connection_type> <connection_string> <admin_server_address> <process_name> <extra_opt> <extra_opt_server_list> <extras_type>
    Örnek : wls_manager.py state secure config_file_path,key_file_path 192.168.1.1:17001,192.168.1.2:17001 restart except Batch2_1,API1_2 app_target
    Seçenekler :
        state_manager için;
            process_name;
                - start
                - stop
                - restart
            exstra_opt;
                - except
                - only
                - none
            eğer exstra_opt none değilse;
                - Virgülle ayrılmış argüman listesi
            extras_type
                - app_target
                - app_name
    Not : extra_opt alanı "except", "only" veya "none" değeri alabilir.Except seçeneği, sonrasında yazacağınız uygulamaları ilgili işleme
        dahil etmeyecektir.Only seçeneği, yalnızca sonrasında yazılı olan uygulamalarda istenilen işlemleri yapacaktır.None seçeneği
        admin server üzerinde yer alan tüm uygulamalar için işlem yapacaktır.(AdminServer hariç). Extras_type parametresi, keninden önce gelen parametreyi niteler.
        Yani target yada appname olduğunu belirtir.Eğer app_name ise, ilgili uygulamaya ait targetlar otomatik bulunur.
"""

import datetime
import time
import sys
import os

shutdown_process = []
start_process = []
correct_state_dict = {
    "start": "RUNNING",
    "shutdown": "SHUTDOWN"
}


def connect_admin_server(conn_args, addr, type="plain"):
    write_log_file("Admin server bağlantısı yapılıyor.Admin server => %s" % str(addr), "INFO")
    try:
        if type == "plain":
            connect(conn_args["user"], conn_args["passwd"], "t3://"+addr)
        else:
            connect(userConfigFile=conn_args["config_file"],
                    userKeyFile=conn_args["key_file"],
                    url="t3://" + addr)
    except WLSTException:
        write_log_file("Admin server bağlantısı sırasında bir hata alındı.Username/password yada adres hatalı", "ERROR", last=True)

def close_conn():
    write_log_file("Admin server bağlantısı kapatılıyor.", "INFO")
    disconnect()

def target_is_live(target):
    domainRuntime()
    if cmo.lookupServerLifeCycleRuntime(target).getState() == "RUNNING":
        return True
    return False

def get_target_state(target):
    domainRuntime()
    return cmo.lookupServerLifeCycleRuntime(target).getState()

def find_target_for_apps(app_names):
    serverConfig()
    target_list = []
    if isinstance(app_names, list):
        for app_name in app_names:
            target_list.extend([i for i in ls("AppDeployments/" + app_name + "/Targets", returnMap='true', returnType="c")])
    elif isinstance(app_names, str):
        target_list.extend([i for i in ls("AppDeployments/" + app_names + "/Targets", returnMap='true', returnType="c")])
    return target_list

def stop_app_target(target):
    if target_is_live(target):
        serverConfig()
        s = shutdown(target, force="true", block="false")
        shutdown_process.append((s, target))
        return True

def start_app_target(target):
    if not target_is_live(target):
        serverConfig()
        s = start(target, block="false")
        start_process.append((s, target))
        return True

def wait_until_list_empty(t_list, process):
    #TODO eğer düzgün bir şekilde açılmadıysa yeniden açılış işlemine göndermek için iyileştirme yapalım.
    # if not_start_correctly(t[1]) and not_ok_healt(t[1]):
    #   start_app_target(t[1])
    import time
    prc_dict = {
        "start": start_app_target,
        "shutdown": stop_app_target
    }
    s_sec = 15 if process == "shutdown" else 60
    while len(t_list) > 0:
        for t in t_list:
            try:
                if t[0].isRunning() == 0:
                    t_list.remove(t)
            except AttributeError:
                if get_target_state(t[1]) != correct_state_dict[process]:
                    prc_dict[process](t[1])
                else:
                    t_list.remove(t)
        write_log_file("Uygulama %s işlemleri sürüyor.Kalan uygulama sayısı => %s" %(process, str(len(t_list))), "INFO")
        time.sleep(s_sec)
    return True

def get_target(process, app_list):
    target = []
    if process == "none":
        target = [i for i in ls("Targets", returnMap='true', returnType="c") if i != "AdminServer"]
    elif process == "except":
        app_list.append("AdminServer")
        target = [i for i in ls("Targets", returnMap='true', returnType="c") if i not in app_list]
    elif process == "only":
        target = [i for i in ls("Targets", returnMap='true', returnType="c") if i in app_list]
    return target

def get_app_names_on_admin(app_names):
    return [i for i in ls("AppDeployments", returnMap='true', returnType="c") if i in app_names]

def timestamp():
    return datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

def write_log_file(log, level, first=False, last=False):
    log_file = open("/home/wasadm/staging_restart.log", "a")
    if first:
        log_file.write("*"*130)
        log_file.write("\n")
    log_file.write(
        "%s [%s] %s\n" %(str(timestamp()), level, log)
    )
    if last:
        log_file.write("*" * 130)
        log_file.write("\n\n")
    log_file.close()

def prepare_conn_string(conn_string, type):
    conn_dict = {}
    if type == "plain":
        conn_dict = {
            "user": conn_string[0],
            "passwd": conn_string[1]
        }
    elif type == "secure":
        conn_dict = {
            "config_file": conn_string[0],
            "key_file": conn_string[1]
        }
    return conn_dict

def stoping_proccess(targets):
    # Admin server üzerindeki tüm targetlar çekilir.
    write_log_file("Uygulamalar kapatılıyor.Uygulamalar => %s" % str(", ".join(targets)), "INFO")
    for target in targets:
        stop_app_target(target)
    # Tüm uygulamalar kapanıncaya kadar bekle
    if len(shutdown_process) > 0:
        write_log_file("Uygulamaların kapanması bekleniyor.", "INFO")
        wait_until_list_empty(shutdown_process, "shutdown")
    write_log_file("Uygulamalar kapandı.", "INFO")

def starting_process(targets):
    # Admin server üzerindeki tüm targetlar çekilir.
    write_log_file("Uygulamalar açılıyor.Uygulamalar => %s" % str(", ".join(targets)), "INFO")
    for target in targets:
        start_app_target(target)
    # Tüm uygulamalar açılıncaya kadar bekle
    if len(start_process) > 0:
        write_log_file("Uygulamalar açılması bekleniyor.", "INFO")
        wait_until_list_empty(start_process, "start")
    write_log_file("Uygulamalar açıldı.", "INFO")

def restarting_process(targets):
    stoping_proccess(targets)
    starting_process(targets)

def undeploy_application(app_name, target_list):
    write_log_file("Uygulama kaldırılıyor.Uygulama => %s, Hedefler => %s" %(app_name, ", ".join(target_list)), "INFO")
    undeploy(app_name, targets=",".join(target_list))
    write_log_file("Uygulama kaldırıldı.", "INFO")
    return True

def deploy_application(app_name, target_list, src_path, ext):
    import os
    write_log_file("Uygulama yükleniyor.Uygulama => %s, Hedefler => %s" % (app_name, ", ".join(target_list)), "INFO")
    deploy(app_name, os.path.join(src_path, "%s.%s" %(app_name, ext)), targets=",".join(target_list), upload="true")
    write_log_file("Uygulama yüklendi.", "INFO")
    return True

def get_application_state(app_names):
    domainRuntime()
    cd('AppRuntimeStateRuntime/AppRuntimeStateRuntime')
    if isinstance(app_names, list):
        error_state = {}
        for app in app_names:
            state = cmo.getIntendedState(app)
            if state != "STATE_ACTIVE":
                error_state[app] = state
        if len(error_state) > 0:
            return False, error_state
        return True, 0
    elif isinstance(app_names, str):
        state = cmo.getIntendedState(app_names)
        if state != "STATE_ACTIVE":
            return False, state
        return True, 0

def server_state_manager(conn_element, conn_type, args):
    write_log_file("State manager çalışmaya başlıyor.Seçilen işlem => %s" % (str(args[1].upper())), "INFO")
    process_list = {
        "start": starting_process,
        "stop": stoping_proccess,
        "restart": restarting_process
    }
    extra_opt = args[2]
    process_name = args[1]
    admin_addrs = args[0].split(",")
    for admin in admin_addrs:
        connect_admin_server(conn_element, admin, conn_type)
        if extra_opt != "none":
            extras_type = args[4]
            if extras_type == "app_name":
                target_list = get_target(extra_opt, find_target_for_apps(args[3].split(",")))
            else:
                target_list = get_target(extra_opt, args[3].split(","))
        else:
            target_list = get_target(extra_opt, None)
        process_list[process_name](target_list)
        close_conn()
    write_log_file("Çalışma sona erdi.", "INFO", last=True)

def application_deployment_manager(conn_element, conn_type, args, retry_count=0):
    write_log_file("Deploy manager çalışmaya başlıyor.Deploymen tipi => %s" % str(args[1].upper()), "INFO")
    admin_addrs = args[0].split(",")
    src_path = args[3]
    src_extension = args[4]
    for admin in admin_addrs:
        connect_admin_server(conn_element, admin, conn_type)
        app_names = get_app_names_on_admin(args[2].split(","))
        targets_on = get_target("only", find_target_for_apps(app_names))
        stoping_proccess(targets_on)
        for app in app_names:
            targets = find_target_for_apps(app)
            undeploy_application(app, targets)
            deploy_application(app, targets, src_path, src_extension)
        starting_process(targets_on)
        deployment_state = get_application_state(app_names)
        if retry_count < 3:
            if not deployment_state[0]:
                write_log_file("Uygulama düzgün olarak deploy edilemedi.Yeniden denenecek.Uygulamalar ve stateler => %s" % ", ".join(["%s:%s" %(k, v) for k, v in deployment_state[1].iteritems()]),
                               "WARNING")
                args[2] = ",".join([i for i in deployment_state[1].keys()])
                return application_deployment_manager(conn_element, conn_type, args, retry_count+1)
        retry_count = 0
        close_conn()
    write_log_file("Çalışma sona erdi.", "INFO", last=True)


def main():
    #TODO usage() foksiyonu yazılacak.
    args = sys.argv
    if len(args) < 7:
        write_log_file("Argümanlar eksik.Argüman sayısı en az 7 olmalıdır..", "ERROR", last=True)
        sys.exit(1)
    usable_options = {
        "state": server_state_manager,
        "deploy": application_deployment_manager
    }
    if args[1] not in usable_options:
        write_log_file("Girilen seçenek için kullanılabilir işlem bulunmuyor.Seçenek => %s" % args[1], "ERROR", last=True)
        sys.exit(2)
    write_log_file("Çalışma başlatılıyor.Yönetim portalı => %s MANAGER" %(str(args[1].upper())), "INFO", first=True)
    conn_type = args[2]
    conn_element = prepare_conn_string(args[3].split(","), conn_type)
    if conn_type == "secure":
        for path in conn_element.values():
            if not os.path.exists(path):
                write_log_file("Config/Key file için girilen path bulunamadı.Hatalı path => %s" % str(path), "ERROR",
                               last=True)
                sys.exit(3)
    usable_options[args[1]](conn_element, conn_type, args[4:])

main()