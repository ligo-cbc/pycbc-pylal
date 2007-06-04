import sys
from glue.ligolw import ligolw
from glue.ligolw import table
from glue.ligolw import lsctables
from glue.ligolw import utils
from pylal.tools import XLALCalculateEThincaParameter
import numpy

########################################
# helper functions

def uniq(list):
  """
  Return the unique items of a list, preserving order.
  http://mail.python.org/pipermail/tutor/2002-March/012930.html
  """
  temp_dict = {}
  return [temp_dict.setdefault(e,e) for e in list if e not in temp_dict]

def simpleEThinca(trigger1, trigger2):
  ''' 
  Return the distance in parameter space between two inspiral triggers.

  The number returned is only an approximation to the true distance, which is
  valid whenever the two triggers are nearby. This is a simplified version of
  the e-thinca parameter.

  d_average=(1/2)[(Gamma(x1)_{ij}(x2-x1)^i(x2-x1)^j)^(1/2) + (Gamma(x2)_{ij}(x2-x1)^i(x2-x1)^j)^(1/2)]
  @param trigger1, trigger2 are single inspiral triggers.
  '''
  #dend_time = (trigger2.end_time - trigger1.end_time) +\
  #(trigger2.end_time_ns - trigger1.end_time_ns)*10**(-9)
  #print dend_time
  dend_time=(trigger2.end_time_ns - trigger1.end_time_ns)*10**(-9)

  dtau0=trigger2.tau0-trigger1.tau0
  #print dtau0

  dtau3=trigger2.tau3-trigger1.tau3
  #print dtau3

  delta_x = numpy.array([dend_time, dtau0, dtau3])

  Gamma1 = numpy.array( [[trigger1.Gamma0, trigger1.Gamma1, trigger1.Gamma2],\
                 [trigger1.Gamma1, trigger1.Gamma3, trigger1.Gamma4],\
                 [trigger1.Gamma2, trigger1.Gamma4, trigger1.Gamma5]])
  #print Gamma1

  Gamma2 = numpy.array( [[trigger2.Gamma0, trigger2.Gamma1, trigger2.Gamma2],\
                 [trigger2.Gamma1, trigger2.Gamma3, trigger2.Gamma4],\
                 [trigger2.Gamma2, trigger2.Gamma4, trigger2.Gamma5]])
  #print Gamma2

  average_distance= 0.5*numpy.sqrt(numpy.dot(delta_x, numpy.dot(Gamma1, delta_x))) + \
                    0.5*numpy.sqrt(numpy.dot(delta_x, numpy.dot(Gamma2, delta_x)))

  return average_distance

########################################
class coincStatistic:
  """
  This class specifies the statistic to be used when dealing with coincident events.
  It also contains parameter for such cases as the BBH bitten-L statistics.
  """

  __slots__ = ["name","a","b","rsq","bl"]

  def __init__(self, name, a=0, b=0):
    self.name=name
    self.a=a
    self.b=b
    self.rsq=0
    self.bl=0

  def get_bittenl(self, bl, snr ):
    blx=self.a*snr-self.b
    if bl==0:    
      return blx
    else:
      return min(bl, blx)  
    

#######################################
class coincInspiralTable:
  """
  Table to hold coincident inspiral triggers.  Coincidences are reconstructed 
  by making use of the event_id contained in the sngl_inspiral table.
  The coinc is a dictionary with entries: G1, H1, H2, L1, event_id, numifos, 
  stat.  
  The stat is set by default to the snrsq: the sum of the squares of the snrs 
  of the individual triggers.
  """
  class row(object):
    __slots__ = ["event_id", "numifos","stat","likelihood","G1","H1","H2",\
                 "L1","T1","V1","sim","rsq","bl"]
    
    def __init__(self, event_id, numifos = 0, stat = 0, likelihood = 0):
      self.event_id = event_id
      self.numifos = numifos
      self.stat = stat
      self.likelihood = likelihood
      self.rsq=0
      self.bl=0
      
    def add_trig(self,trig,statistic):
      # Coincidence IDs are intended to be unique.  If there is a collision,
      # multiple triggers from the same ifo can get mixed together.  This is
      # a serious problem.  This won't detect all cases, but with more and
      # more triggers being added, it becomes increasingly likely that
      # we'll notice and halt the program.
      assert not hasattr(self, trig.ifo), "Trying to add %s trigger to a"\
        " coincidence for the second time. Coincidence so far:\n%s"\
        "\n\nTrigger:\n%s" % (trig.ifo, dict([(x, getattr(self, x)) for x in \
        self.__slots__ if hasattr(self, x)]), trig.event_id)
      
      self.numifos +=1
      if statistic.name == 'effective_snr':
        self.stat = (self.stat**2 + trig.get_effective_snr()**2)**(1./2)      
      elif 'bitten_l' in statistic.name:
        snr=trig.snr
        self.rsq= (self.rsq**2 + snr**2)**(1./2)
        self.bl=statistic.get_bittenl( self.bl, snr )
        self.stat=min( self.bl, self.rsq )
        if statistic.name == 'bitten_lsq' and self.numifos >2:
          self.stat = self.rsq

      else:
        self.stat = (self.stat**2 + getattr(trig,statistic.name)**2)**(1./2)
      
      # sets the data for the single inspiral trigger
      setattr(self,trig.ifo,trig)
      
    def add_sim(self,sim):
      setattr(self,"sim",sim)

    def get_ifos(self): 
      ifolist = ['G1','H1','H2','L1','T1','V1']
      ifos = ""
      ifolist_in_coinc = []
      for ifo in ifolist:
        if hasattr(self,ifo):
          ifos = ifos + ifo
          ifolist_in_coinc.append(ifo)

      return ifos,ifolist_in_coinc
  
  def __init__(self, inspTriggers = None, stat = None):
    """
    @param inspTriggers: a metaDataTable containing inspiral triggers 
                         from which to construct coincidences
    @param stat:         an instance of coincStatistic
    """
    self.stat = stat
    self.sngl_table = inspTriggers
    self.sim_table = None
    self.rows = []
    if inspTriggers is None:
      return

    # At present, coincidence is recorded by thinca by over-writing event_ids.
    # The event_ids uniquely label coincidences now, rather than triggers.
    row_dict = {}
    unique_id_list = []
    for trig in inspTriggers:
      event_id = trig.event_id
      if event_id not in row_dict:
        unique_id_list.append(event_id)
        row_dict[event_id] = self.row(event_id)
      row_dict[event_id].add_trig(trig, stat)

    # make sure that there are at least two ifos in each coinc; restore order
    pruned_rows = [row_dict[k] for k in unique_id_list \
      if row_dict[k].numifos > 1]

    self.rows = pruned_rows
    
  def __len__(self):
    return len(self.rows)
  
  def append(self,row):
    self.rows.append(row)

  def extend(self,rows):
    self.rows.extend(rows)

  def __getitem__(self, i):
    """
    Retrieve the value in this column in row i.
    """
    return self.rows[i]

  def getstat(self):
    stat = []
    for coinc in self.rows:
      stat.append(coinc.stat)
    return numpy.asarray(stat)

  def sort(self, descending = True):
    """
    Sort the list based on stat value 
    default is to descending
    """
    stat_list = [ (coinc.stat, coinc) for coinc in self.rows ]
    stat_list.sort()
    if descending:
      stat_list.reverse()
    self.rows = [coinc for (stat,coinc) in stat_list]

  def get_slide_numbers(self):
    """
    Return all the slides numbers present in the table.
    """
    nums = uniq(map(lambda c: (c.event_id % 1000000000) // 100000, self.rows))
    for i,num in enumerate(nums):
      if num > 5000:
        nums[i] = 5000 - num
    nums.sort()
    return nums

  def getslide(self, slide_num):
    """
    Return the triggers with a specific slide number.
    @param slide_num: the slide number to recover (contained in the event_id)
    """
    slide_coincs = coincInspiralTable(stat=self.stat)
    slide_coincs.sngl_table = self.sngl_table
    if slide_num < 0:
      slide_num = 5000 - slide_num
    for coinc in self.rows:
      if ( (coinc.event_id % 1000000000) // 100000 ) == slide_num:
        slide_coincs.rows.append(coinc)
     
    return slide_coincs 

  def coincinclude(self, ifolist):
    """
    Return the coincs which have triggers from the ifos in ifolist.
    @param ifolist: a list of ifos 
    """
    selected_coincs = coincInspiralTable(stat=self.stat)
    selected_coincs.sngl_table = self.sngl_table
    for coinc in self:
      keep_trig = True
      for ifo in ifolist:
        if hasattr(coinc,ifo) == False:
          keep_trig = False
          break
            
      if keep_trig == True:
        selected_coincs.append(coinc)
        
    return selected_coincs

  def coinctype(self, ifolist):
    """
    Return the coincs which are from ifos.
    @param ifos: a list of ifos 
    """
    coincs = self.coincinclude(ifolist)
    selected_coincs = coincInspiralTable()
    selected_coincs.sngl_table = self.sngl_table
    for coinc in coincs:
      if coinc.numifos == len(ifolist):
        selected_coincs.append(coinc)
        
    return selected_coincs

    
  def getsngls(self, ifo):
    """
    Return the sngls for a specific ifo.
    @param ifo: ifo for which to retrieve the single inspirals.
    """
    from glue.ligolw import table 
    try: ifoTrigs = table.new_from_template(self.sngl_table)
    except: ifoTrigs = lsctables.New(lsctables.SnglInspiralTable)
    for coinc in self:
      if hasattr(coinc,ifo): 
        ifoTrigs.append(getattr(coinc,ifo))
        
    return ifoTrigs


  def cluster(self, cluster_window):
    """
    Return the clustered triggers, returning the one with the largest stat in 
    each fixed cluster_window
    
    @param cluster_window: length of time over which to cluster (seconds)
    """
    ifolist = ['G1','H1','H2','L1','T1','V1']
    # find times when there is a trigger
    cluster_times = []
    for coinc in self:
      for ifo in ifolist:
        if hasattr(coinc,ifo):
          end_time = getattr(coinc,ifo).end_time
          break
      cluster_times.append(cluster_window * (end_time//cluster_window) )
    cluster_times = uniq(cluster_times)
    
    cluster_triggers = coincInspiralTable(stat = self.stat)
    cluster_triggers.sngl_table = self.sngl_table
    for cluster_time in cluster_times:
      # find all triggers at that time
      cluster = coincInspiralTable()
      for coinc in self:
        for ifo in ifolist:
          if hasattr(coinc,ifo):
            end_time = getattr(coinc,ifo).end_time
            break
        if ((end_time - cluster_time) < cluster_window):   
          cluster.append(coinc)

      # find loudest trigger in time and append
      loudest_stat = 0
      for trigger in cluster:
        if trigger.stat > loudest_stat:
          loudest_trig = trigger
          loudest_stat = trigger.stat

      cluster_triggers.append(loudest_trig)
      
    return cluster_triggers 
  
  def add_sim_inspirals(self,sim_inspiral):
    """
    FIXME: We should really store the sim coincidence info in the event_id
    Method to add simulated injections to a list of coincs

    @param sim_inspiral: a simInspiralTable
    """
    self.sim_table = sim_inspiral
    # check that the number of sims matches the number of coincs:
    if len(self) != len(sim_inspiral):
      print >> sys.stderr, "Number of injections doesn't match number of coincs"
      sys.exit(1)

    for i in range(len(self)):
      self[i].add_sim(sim_inspiral[i])


  def add_missed_sims(self,sim_inspiral):
    """
    Add missed sim inspirals to the list of coincs, set the stat = -1
    @param sim_inspiral: a simInspiralTable
    """
    for sim in sim_inspiral:
      row = coincInspiralTable.row(-1,stat=-1)
      row.add_sim(sim)
      self.append(row)

  def return_sim_inspirals(self,thresh = 0):
    """
    Method to return the sim_inspiral table associated to the coincs.
    If thresh is specified, only return sims from those coincs whose stat
    exceeds thresh.

    @param thresh: the threshold on the statistic
    """
    from glue.ligolw import table 
    simInspirals = table.new_from_template(self.sim_table)
    try: simInspirals = table.new_from_template(sim.sngl_table)
    except: simInspirals = lsctables.New(lsctables.SimInspiralTable)
    for coinc in self:
      if (hasattr(coinc,"sim")) and (coinc.stat >= thresh): 
        simInspirals.append(coinc.sim)
    
    return simInspirals
    
  def partition_by_stat(self, threshold):
    """
    Return (triggers with stat < threshold,
            triggers with stat == threshold,
            triggers with stat > threshold).

    The set of (stat == threshold) is of zero measure, but often, as when
    doing something like the loudest event statistic, the threshold is taken
    from a coinc in self.
    """
    stats = self.getstat()

    lesser_coincs = coincInspiralTable(stat=self.stat)
    lesser_coincs.extend([self[i] for i in (stats < threshold).nonzero()[0]])

    equal_coincs = coincInspiralTable(stat=self.stat)
    equal_coincs.extend([self[i] for i in (stats == threshold).nonzero()[0]])

    greater_coincs = coincInspiralTable(stat=self.stat)
    greater_coincs.extend([self[i] for i in (stats > threshold).nonzero()[0]])

    return lesser_coincs, equal_coincs, greater_coincs

  def getTotalMass(self,mLow,mHigh):
    """
    Return triggers with mLow <= mean total mass < mHigh
    @param mLow: a float
    @param mHigh: a float
    """
    triggers_in_mass_range = coincInspiralTable()
    ifolist = ['G1','H1','H2','L1','T1','V1']
    for coinc in self:
      ifos = []
      mass_numer = 0.0
      mass_denom = float(coinc.numifos)
      for ifo in ifolist:
        if hasattr(coinc,ifo):
          mass_numer += getattr(coinc,ifo).mass1 + getattr(coinc,ifo).mass2
      mean_total_mass = mass_numer / mass_denom
      if (mean_total_mass >= mLow) and (mean_total_mass < mHigh):
        triggers_in_mass_range.append(coinc)

    return triggers_in_mass_range

  def getChirpMass(self,mLow,mHigh):
    """
    Return triggers with mLow <= mean chirp mass < mHigh
    @param mLow: a float
    @param mHigh: a float
    """
    triggers_in_mass_range = coincInspiralTable()
    ifolist = ['G1','H1','H2','L1','T1','V1']
    for coinc in self:
      ifos = []
      mass_numer = 0.0
      mass_denom = float(coinc.numifos)
      for ifo in ifolist:
        if hasattr(coinc,ifo):
          mass_numer += getattr(coinc,ifo).mchirp
      mean_total_mass = mass_numer / mass_denom
      if (mean_total_mass >= mLow) and (mean_total_mass < mHigh):
        triggers_in_mass_range.append(coinc)

    return triggers_in_mass_range

  def getEThincaValues(self,ifos):
    """
    Return ethinca values for the coincidences
    @param ifos: a list of the 2 ifos
    """
    ethinca = []
    for coinc in self:
      if ( hasattr(coinc,ifos[0]) == False ) or \
          ( hasattr(coinc,ifos[1]) == False ):
        ethinca.append(0.0)
      else:
        ethinca.append( XLALCalculateEThincaParameter(getattr(coinc,ifos[0]), 
            getattr(coinc,ifos[1]) ) )
    
    return numpy.asarray(ethinca)

  def getSimpleEThincaValues(self, ifos):
    """
    Return simple ethinca values for the coincidences of the ifo pair ifos.
    
    For coincs that do not have both ifos specified, return 0.0.
    """
    ethinca = numpy.zeros(len(self), dtype=float)
    for i,coinc in enumerate(self):
      if hasattr(coinc, ifos[0]) and hasattr(coinc, ifos[1]):
        ethinca[i] = simpleEThinca(getattr(coinc, ifos[0]),
                                   getattr(coinc, ifos[1]))
    return ethinca

  def metricHistogram(self, candidate):
    """
    Return distance squared between candidate and coincident triggers
    using the following metric

    d^2 = ( 1/n ) * sum_i ( |cparam_i - trigparam_i|^2 / cparam_i^2 )

    @param candidate: a coincInspiral describing a candidate
    """
    c_ifos,ifolist = candidate.get_ifos()
    dsquared = []

    for trig in self:
      trig_ifos,tmplist = trig.get_ifos()
      tmp_d_squared = 0.0
      param_counter = 0
      if c_ifos == trig_ifos:
        for ifo1 in ifolist: 
          # distance^2 apart in effective snr
#          c_lambda = getattr(candidate,ifo1).get_effective_snr()
#          t_lambda = getattr(trig,ifo1).get_effective_snr()
#          tmp_d_squared += ( 1.0 - t_lambda / c_lambda )**2
#          param_counter += 1

          # distance^2 apart in mchirp
#          c_lambda = getattr(candidate,ifo1).mchirp
#          t_lambda = getattr(trig,ifo1).mchirp
#          tmp_d_squared += ( 1.0 - t_lambda / c_lambda )**2
#          param_counter += 1

          # distance^2 apart in effective distance
#          c_lambda = getattr(candidate,ifo1).eff_distance
#          t_lambda = getattr(trig,ifo1).eff_distance
#          tmp_d_squared += ( 1.0 - t_lambda / c_lambda )**2
#          param_counter += 1

          # distance^2 apart in ethinca
	  for ifo2 in ifolist:
            if ifo1 < ifo2:
              c_lambda = simpleEThinca(\
              getattr(candidate,ifo1),\
              getattr(candidate,ifo2) )
              t_lambda = simpleEThinca(\
              getattr(trig,ifo1),\
              getattr(trig,ifo2) ) 
              tmp_d_squared += ( 1.0 - t_lambda / c_lambda )**2
              param_counter+=1
#              c_lambda = XLALCalculateEThincaParameter(\
#              getattr(candidate,ifo1),\
#              getattr(candidate,ifo2) ) 
#              t_lambda = XLALCalculateEThincaParameter(\
#              getattr(trig,ifo1),\
#              getattr(trig,ifo2) ) 
#              tmp_d_squared += ( 1.0 - t_lambda / c_lambda )**2

        dsquared.append(tmp_d_squared/param_counter)
      else:
        dsquared.append(-1.0)
    return numpy.asarray(dsquared)


  def getTriggersWithinEpsilon(self, candidate, epsilon):
    """
    Return distance squared between candidate and coincident triggers
    using the following metric

    d^2 = ( 1/n ) * sum_i ( |cparam_i - trigparam_i|^2 / cparam_i^2 )

    @param candidate: a coincInspiral describing a candidate
    """
    c_ifos,ifolist = candidate.get_ifos()
    triggers_within_epsilon = coincInspiralTable()

    for trig in self:
      trig_ifos,tmplist = trig.get_ifos()
      tmp_d_squared = 0.0
      param_counter = 0
      if c_ifos == trig_ifos:
        for ifo1 in ifolist: 
          # distance^2 apart in effective snr
          #c_lambda = getattr(candidate,ifo1).get_effective_snr()
          #t_lambda = getattr(trig,ifo1).get_effective_snr()
          #tmp_d_squared += ( 1.0 - t_lambda / c_lambda )**2
          #param_counter += 1

          # distance^2 apart in mchirp
          #c_lambda = getattr(candidate,ifo1).mchirp
          #t_lambda = getattr(trig,ifo1).mchirp
          #tmp_d_squared += ( 1.0 - t_lambda / c_lambda )**2
          #param_counter += 1

          # distance^2 apart in effective distance
          #c_lambda = getattr(candidate,ifo1).eff_distance
          #t_lambda = getattr(trig,ifo1).eff_distance
          #tmp_d_squared += ( 1.0 - t_lambda / c_lambda )**2
          #param_counter += 1

          # distance^2 apart in ethinca
	  for ifo2 in ifolist:
            if ifo1 < ifo2:
              c_lambda = simpleEThinca(\
              getattr(candidate,ifo1),\
              getattr(candidate,ifo2) )
              t_lambda = simpleEThinca(\
              getattr(trig,ifo1),\
              getattr(trig,ifo2) )

#              c_lambda = XLALCalculateEThincaParameter(\
#              getattr(candidate,ifo1),\
#              getattr(candidate,ifo2) ) 
#              t_lambda = XLALCalculateEThincaParameter(\
#              getattr(trig,ifo1),\
#              getattr(trig,ifo2) ) 
              tmp_d_squared += ( 1.0 - t_lambda / c_lambda )**2
              param_counter += 1

        if ( (tmp_d_squared / float(param_counter)) < epsilon ):
          triggers_within_epsilon.append(trig)

    return triggers_within_epsilon

