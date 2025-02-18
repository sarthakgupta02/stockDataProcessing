from flask import Flask, request, jsonify, send_file, render_template
import pandas as pd
import os
from flask import render_template


app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
PROCESSED_FOLDER = "processed"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

def getCurrentDayData(file_name):
    df = pd.read_csv(file_name)
    df.columns = df.columns.str.strip()
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    df['DATE1'] = pd.to_datetime(df['DATE1'])
    df['DELIV_QTY'] = pd.to_numeric(df['DELIV_QTY'], errors='coerce')
    df['DELIV_PER'] = pd.to_numeric(df['DELIV_PER'], errors='coerce')
    df['DELIV_QTY'] = df['DELIV_QTY'].fillna(0)
    df['DELIV_PER'] = df['DELIV_PER'].fillna(0)
    df = df[(df['SERIES'] == 'BE') | (df['SERIES'] == 'EQ')].reset_index(drop=True)
    return df.loc[:, ['SYMBOL', 'SERIES', 'DATE1', 'CLOSE_PRICE', 'TTL_TRD_QNTY', 'NO_OF_TRADES', 'DELIV_QTY', 'DELIV_PER']]

def processDataAndSave(temp_today, history):
    temp_today.loc[:, ['Flag50']] = ''
    temp_today.loc[:, ['Flag200']] = ''
    temp_today.loc[:, ['FlagVolume']] = ''
    rollingHistory50 = history.loc[:, ['SYMBOL', 'CLOSE_PRICE', 'TTL_TRD_QNTY', 'NO_OF_TRADES', 'DELIV_QTY', 'DELIV_PER']].groupby('SYMBOL').rolling(50).mean()
    rollingHistory200 = history.loc[:, ['SYMBOL', 'CLOSE_PRICE', 'TTL_TRD_QNTY', 'NO_OF_TRADES', 'DELIV_QTY', 'DELIV_PER']].groupby('SYMBOL').rolling(200).mean()
    
    for i in range(len(temp_today)):
        try:
            percent = temp_today.iloc[i]['DELIV_PER']
            symbol = temp_today.iloc[i]['SYMBOL']
            volume = temp_today.iloc[i]['TTL_TRD_QNTY']
            
            if not pd.isna(rollingHistory50.loc[symbol].tail(1)['DELIV_PER'].iloc[0]):
                if percent > rollingHistory50.loc[symbol].tail(1)['DELIV_PER'].iloc[0]:
                    temp_today.loc[i, ['Flag50']] = 'Y'
            else:
                temp_today.loc[i, ['Flag50']] = 'N/A'

            if not pd.isna(rollingHistory200.loc[symbol].tail(1)['DELIV_PER'].iloc[0]):
                if percent > rollingHistory200.loc[symbol].tail(1)['DELIV_PER'].iloc[0]:
                    temp_today.loc[i, ['Flag200']] = 'Y'
            else:
                temp_today.loc[i, ['Flag200']] = 'N/A'

            if not pd.isna(rollingHistory200.loc[symbol].tail(1)['TTL_TRD_QNTY'].iloc[0]):
                if volume > rollingHistory200.loc[symbol].tail(1)['TTL_TRD_QNTY'].iloc[0]:
                    temp_today.loc[i, ['FlagVolume']] = 'Y'
            else:
                temp_today.loc[i, ['FlagVolume']] = 'N/A'

        except KeyError:
            print("First occurrence: " + symbol)
            temp_today.loc[i, ['Flag50']] = 'N/A'
            temp_today.loc[i, ['Flag200']] = 'N/A'
            temp_today.loc[i, ['FlagVolume']] = 'N/A'
    
    return temp_today

def appendToHistoricData(history, current):
    history['DATE1'] = pd.to_datetime(history['DATE1'])
    current['DATE1'] = pd.to_datetime(current['DATE1'])
    history = pd.concat([history, current], ignore_index=True)
    return history

def process_files(historic_path, todays_path):
    try:
        historic_df = pd.read_csv(historic_path)
        today_df = getCurrentDayData(todays_path)

        updated_today_df = processDataAndSave(today_df.copy(), historic_df)
        updated_historic_df = appendToHistoricData(historic_df, today_df)

        updated_historic_path = os.path.join(PROCESSED_FOLDER, "updated_historic.csv")
        processed_today_path = os.path.join(PROCESSED_FOLDER, "processed_today.csv")

        updated_historic_df.to_csv(updated_historic_path, index=False)
        updated_today_df.to_csv(processed_today_path, index=False)

        return updated_historic_path, processed_today_path
    except Exception as e:
        print(f"Error processing files: {e}")
        return None, None

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'historic' not in request.files or 'today' not in request.files:
        return jsonify({"error": "Please upload both historic and today's data files"}), 400

    historic_file = request.files['historic']
    todays_file = request.files['today']

    historic_path = os.path.join(UPLOAD_FOLDER, historic_file.filename)
    todays_path = os.path.join(UPLOAD_FOLDER, todays_file.filename)

    historic_file.save(historic_path)
    todays_file.save(todays_path)

    updated_historic_path, processed_today_path = process_files(historic_path, todays_path)

    if updated_historic_path and processed_today_path:
        return jsonify({
            "message": "Files processed successfully",
            "download_links": {
                "updated_historic": "/download/updated_historic.csv",
                "processed_today": "/download/processed_today.csv"
            }
        })
    else:
        return jsonify({"error": "Error processing files"}), 500

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(PROCESSED_FOLDER, filename), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
