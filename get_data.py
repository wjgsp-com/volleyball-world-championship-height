# -*- coding: utf-8 -*-
"""

Get teams and players data from FIVB website
Exports in two csv files

"""

import os
import subprocess
import re
import time

import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By

import pandas as pd


def start_driver():
    """ Start selenum driver using Firefox

    Kill all running headless Firefox processes
    """
    subprocess.call('pkill -f .*firefox.*-headless.*',shell=True)
    options = webdriver.firefox.options.Options()
    options.headless = True
    # disable image and javascript for faster loading
    options.set_preference('permissions.default.image',2)
    options.set_preference('javascript.enabled',False)
    driver = webdriver.Firefox(options=options)
    # waiting time to load page, avoiding pipe error
    driver.set_page_load_timeout(10.0)
    #driver.implicitly_wait(.025)

    return driver


def read_teams_data(driver,):
    """ Read teams data
    """
    
    website = 'https://en.volleyballworld.com/volleyball/competitions'
    homepage_url = f'{website}/women-worldchampionship-2022/teams/'
    standing_url = f'{website}/women-worldchampionship-2022/standings/#round-f'

    # opening page
    print('Opening page')
    print(homepage_url)
    driver.get(homepage_url)

    results = driver.find_elements(By.CLASS_NAME,'d3-l-col__col-2')
    number_teams = len(results)
    
    # create empty pandas dataframe for team data
    teams_df = pd.DataFrame(
        columns=['team_name','team_abbreviation','team_id','team_url',],
        index=range(number_teams)
        )
    for i, result in enumerate(results):
        name = result.get_attribute('alt')
        url = result.get_attribute('href')
        number = url.split('/')[-3]
        abbr = result.find_element(
            By.CLASS_NAME,'vbw-mu__team__name--abbr'
            ).get_attribute('innerHTML')
        print('\x1b[2K',f' - {name}',end='\r')
        teams_df.loc[i] = [name,abbr,number,url,]

    teams_df.set_index('team_name',inplace=True)

    # reading final standing
    print('\x1b[2K',standing_url)
    driver.get(standing_url)

    teams_rows = driver.find_elements(
        By.XPATH,
        '/html/body/div[1]/main/section[2]'
        '/div/div/div/div/div[3]/div/div/div/div/table/tbody/tr'
    )
    teams_df['rank'] = [0]*len(teams_df)
    # getting players' page url and initial information
    for rank, team_row in enumerate(teams_rows):
        element = team_row.find_element(By.CLASS_NAME,'vbw-mu__team__name')
        team_element = element.get_attribute('innerHTML')
        team_id = re.findall(r'\d+', team_element)[-1]
        # get player web page from link
        teams_df.loc[teams_df['team_id'] == team_id,'rank'] = rank + 1
    
    return teams_df


def read_players_stats(driver,teams_df):
    """ Read player stats (weight, height, points)
    """

    count_players = 0
    print('Reading players data...')
    # open teams pages to get list of players of each team
    for team_page in teams_df['team_url']:#[:1]:
        team_players_page = team_page.replace('schedule','players')
        driver.get(team_players_page)
        players_rows = driver.find_elements(
           By.XPATH,'//html/body/div[1]/main/section[2]/div/div/div/table/tbody/tr'
           )
        
        # getting players' page url and initial information
        players_initial_info = []
        player_data = {}
        for player_row in players_rows:
            cells = player_row.find_elements(By.CLASS_NAME,'d3-l-col__col-2')
            # get player web page from link
            player_data['url'] = cells[0].get_attribute('href')
            # get initial player data (better here than on player's page)
            for cell, field in zip(cells,('number','name','position')):
                player_data[field] = cell.get_attribute('innerHTML')
            players_initial_info.append(player_data.copy())
        # rename position because the full name will be available later
        player_data['position_abbreviation'] = player_data['position']
        player_data.pop('position')

        for player_info in players_initial_info:
            player_data = {}
            player_data.update(player_info)
            # go to player page
            driver.get(player_data['url'])

            # reading bio and stats
            for type in ('bio','stats'):
                cols = driver.find_elements(By.CLASS_NAME,f'vbw-player-{type}-col')
                for col in cols:
                    try:
                        field = col.find_element(
                            By.CLASS_NAME,f'vbw-player-{type}-head').get_attribute(
                                'innerHTML')
                        val = col.find_element(
                            By.CLASS_NAME,f'vbw-player-{type}-text').get_attribute(
                                'innerHTML')
                        # remove units inside span tag and tag itself
                        val = re.sub('<span.*>.*</span>','',val)
                        if val == '-' or val is None:
                            # replace non-defined values (averages and succes 
                            # ratios) by null
                            val = 0.0
                        
                        # harmonize name, make it snake case
                        field = field.lower().replace(' ','_')
                        
                        # preffix with the previous field name if 'points' is
                        # missing from the name
                        if 'average' in field or 'efficiency' in field \
                            or 'success'  in field or 'avg' in field:
                            field = f'{base_field}_{field}' 
                        else:
                            base_field = field

                        player_data[field] = val
                    except(selenium.common.exceptions.NoSuchElementException):
                        # add exception because some values are wrapped
                        # no need to store them because the data is extracted
                        # elsewhere
                        pass

            print('\x1b[2K',
                  player_data['nationality'],'-',player_data['name'],
                  end='\r'
                )

            player_id = player_data['url'].split('/')[-1]
            if count_players == 0: # not very wise
                # create players dataframe
                players_df = pd.DataFrame(
                    columns=player_data.keys(),
                    data=[player_data.values()],
                    index=[player_id],
                    )
                players_df.index.name = 'player_id'
            else:
                players_df.at[player_id] = player_data
    
            count_players += 1

    # "fixing" Gabriela Orvosova position
    # as in European Volleyball Confederation (CEV) website
    # https://www.cev.eu/national-team/european-league/european-golden-league/women/team/12119-czech-republic/player/74064-orvosova-gabriela
    players_df.loc['168827','position'] = 'Opposite spiker'
    
    return players_df


if __name__ == '__main__':
    
    data_folder = './data'
    if not os.path.exists(data_folder):
        os.makedirs(data_folder)
    
    driver = start_driver()
 
    teams_df = read_teams_data(driver,)
    players_df = read_players_stats(driver,teams_df)

    # remove url - not used further
    teams_df = teams_df.drop('team_url',axis=1)
    teams_df.to_csv(os.path.join(data_folder,'teams.csv'))
    players_df = players_df.drop('url',axis=1)
    players_df.to_csv(os.path.join(data_folder,'players.csv'))

    driver.quit()

    print('\x1b[2K','Done.')