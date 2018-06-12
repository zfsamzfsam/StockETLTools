import pandas as pd
from datasync.data_origin import DataOrigin
from jaqs.data.dataservice import RemoteDataService
import warnings
warnings.filterwarnings("ignore")

class DataServiceOrigin(DataOrigin):
    def __init__(self, db_config):
        super(DataServiceOrigin, self).__init__(db_config)
        self.conn = None
        self.ds_props = None
        self.connect(db_config)

    def connect(self,db_config):
        self.ds_props = {'remote.data.address': db_config['addr'],
                        'remote.data.username': db_config['user'],
                        'remote.data.password': db_config['password'],
                         "timeout":600}
        try:
            ds = RemoteDataService()
            ds.init_from_config(self.ds_props)
            self.conn = ds
        except:
            raise ValueError('数据库连接失败，请检查配置信息是否正确')

    def all_symbol(self,start_date,end_date,add_index=False):
        symbol = self.conn.query_index_member('000001.SH', start_date, end_date) + \
                 self.conn.query_index_member('399106.SZ',start_date,end_date)
        symbol = [i for i in symbol if i[0] != '2' and i[0] != '9']

        if add_index:
            df1, msg = self.conn.query(view="jz.instrumentInfo",
                                          fields="symbol",
                                          filter="market=SH&inst_type=100",
                                          data_format='pandas')

            df2, msg = self.conn.query(view="jz.instrumentInfo",
                                      fields="symbol",
                                      filter="market=SZ&inst_type=100",
                                      data_format='pandas')
            index = list(df1['symbol']) + list(df2['symbol'])
            symbol.extend(index)
        return symbol

    def read(self, props=None, sql=None,limit = 1000):
        view = props.pop('view')
        field = props.pop('fields')
        start_date = props['start_date']
        end_date = props['end_date']
        if view == 'STOCK_D':
            symbol = self.all_symbol(start_date,end_date,add_index=True)
        else:
            symbol = self.all_symbol(start_date,end_date,add_index=False)
        dates = self.conn.query_trade_dates(start_date, end_date)

        num = len(symbol)

        def distributed_query(i):
            data = None
            if i * limit < num:
                pos1, pos2 = int(i * limit), int((i + 1) * limit)
                s = symbol[pos1:pos2]
                s = ','.join(s)

            _filter = 'symbol={}&start_date={}&end_date={}'.format(s, start_date, end_date)
            if view == 'STOCK_D':
                while True:
                    try:
                        self.conn.init_from_config(self.ds_props)
                        data, msg = self.conn.daily(s, start_date, end_date, fields=field, adjust_mode=None)
                        if msg == "0,":
                            break
                    except:
                        print('query faild, retry')


            elif view == 'factors':
                while True:
                    try:
                        self.conn.init_from_config(self.ds_props)
                        data, msg = self.conn.query(view='factor', fields=field, filter=_filter, data_format='pandas')
                        if msg == "0,":
                            break
                    except:
                        print('query faild, retry')

            elif view == 'SecDailyIndicator':
                #data, msg = self.conn.query_lb_dailyindicator(s, start_date, end_date, fields=field)

                while True:
                    try:
                        self.conn.init_from_config(self.ds_props)
                        data, msg = self.conn.query_lb_dailyindicator(s, start_date, end_date, fields=field)
                        if msg == "0,":
                            break
                    except:
                        print('query faild, retry')


            elif view == 'adjust':
                dic = {}
                for i in field.split(','):
                    if i not in ['symbol','trade_date']:
                        dic[i[:-4]] = i
                fld = ','.join(list(dic.keys()))

                while True:
                    try:
                        self.conn.init_from_config(self.ds_props)
                        data, msg = self.conn.daily(s, start_date, end_date, fld, adjust_mode='post')
                        if msg == "0,":
                            break
                    except:
                        print('query faild, retry')


                fld = list(set(fld.split(',') + ['trade_date', 'symbol']))
                data = data.loc[:, fld]
                data = data.rename(dic, axis=1)

            elif view == 'adjust_factor':
                data = self.conn.query_adj_factor_daily(s, start_date, end_date)
                data = data.stack().reset_index()
                data.columns = ['trade_date','symbol','adjust_factor']
            return data

        l = []
        import math
        for i in range(math.ceil(num / limit)):
            n = len(l)
            while True:
                try:
                    data = distributed_query(i)
                    l.append(data)
                    break
                except:
                    print('query faild, retry')
                    self.conn.init_from_config(self.ds_props)
                    data = distributed_query(i)
                    if data is not None:
                        l.append(data)
                        break
        df = pd.concat(l)
        return df

def test():
    #props = {'start_date': 20180301, 'end_date': 20180501, 'fields':'adjust_factor' , 'view':'adjust_factor'}
    props = {'start_date': 20180301, 'end_date': 20180501, 'fields': 'open_adj,low_adj', 'view': 'adjust'}
    db_config = {'addr':'tcp://192.168.0.102:23000','user':'1','password':'2'}

    dso = DataServiceOrigin(db_config)
    data = dso.read(props = props)
    print (data)

#if __name__ == '__main__':
#    test()