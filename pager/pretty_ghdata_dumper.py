def pretty(data):
    for repo in data:
        for name, info in repo.items():
            print(name)
            for key, value in info.items():
                if value.__class__.__name__ == 'list':
                    print("    %s:" % key)
                    for val in value:
                        if key == 'commits':
                            for k, v in val.items():
                                print("        %s: %s" % (k, val[k]))
                        else:
                            print("        %s" % val)
                        print("        ...")
                else:
                    print("    repo last updated (%s): %s" % (key, info[key]))
            print("___________________")